"""
Phase 1 v2 · LLM 信号识别（默认主流程）

每条 review 用 LLM (DeepSeek 默认) 按 N 信号定义打 0/1/2 分，
按 segment 聚合 → segment_pricing_summary.csv，Phase 2 直接用。

vs 旧 phase1 (cluster-aggregated proxy):
  · review-level 精度而非 cluster-aggregated
  · 信号 ground truth，无需事后校准
  · 不依赖 keyword 匹配 (PAIN_KEYWORD_MAP / PERSONA_PRIORS)

输入:
  --reviews-csv     竞品 + (可选) Reddit reviews CSV (含 row_id/text/segment_label/source)
  --config          品类配置 JSON
  --output-dir      落盘目录

输出:
  llm_signal_scores.parquet           每 review × N 信号
  segment_pricing_summary.csv         segment × N 信号（Phase 2 直接读）

环境变量: DEEPSEEK_API_KEY
"""

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from openai import OpenAI


def build_prompt(signals: dict) -> str:
    """从品类配置的 signals 字典构造 LLM 标注 prompt。"""
    bullet = []
    for i, (sig_id, sig_def) in enumerate(signals.items(), 1):
        desc = sig_def.get("description") or sig_def.get("label") or sig_id.replace("_score", "").replace("_", " ")
        bullet.append(f"{i}. {sig_id} — {desc}")
    return f"""请按以下 {len(signals)} 个信号给每条评论打 0/1/2 分
（0=无证据，1=弱证据，2=强证据）：

{chr(10).join(bullet)}

每个信号必须给 0、1、或 2。不确定时给 0。
输出严格 JSON 格式，键名与信号名完全一致。例：
{{"{list(signals.keys())[0]}": 0, "{list(signals.keys())[1]}": 1, ...}}

只输出 JSON，不要任何解释文字。"""


def annotate_one(client: OpenAI, row: dict, system_prompt: str,
                  signal_ids: list, model: str) -> dict:
    text = str(row.get("text", "")).strip()[:1200]
    title = str(row.get("title", "")).strip()
    persona = str(row.get("persona", "")).strip()[:300]
    user_msg = f"""评论标题: {title or '(无)'}

评论正文:
{text}

中文 persona 分析（参考，可能为空）:
{persona or '(无)'}

按信号定义给 0/1/2 分，输出 JSON。"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.1, max_tokens=600,
        )
        scores = json.loads(resp.choices[0].message.content)
        result = {"row_id": row["row_id"]}
        for sig in signal_ids:
            v = scores.get(sig, 0)
            try:
                v = int(v)
                v = max(0, min(2, v))
            except Exception:
                v = 0
            result[sig] = v
        return result
    except Exception as e:
        result = {"row_id": row["row_id"], "_error": str(e)[:120]}
        for sig in signal_ids:
            result[sig] = 0
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reviews-csv", required=True,
                   help="标准化 reviews CSV: row_id/text/title/persona/segment_label/source")
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--concurrency", type=int, default=15)
    p.add_argument("--model", default="deepseek-chat")
    p.add_argument("--api-base", default="https://api.deepseek.com/v1")
    p.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    p.add_argument("--checkpoint-every", type=int, default=200)
    p.add_argument("--limit", type=int, default=0,
                   help="0 = 全量；非 0 = 仅取前 N 条（调试用）")
    args = p.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"缺 {args.api_key_env} 环境变量")

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.config).read_text())
    signals = config["signals"]
    signal_ids = list(signals.keys())
    system_prompt = "你是消费电子市场评论分析专家。任务：阅读每条用户评论，按信号定义给 0/1/2 分。\n\n" + build_prompt(signals)

    df_in = pd.read_csv(args.reviews_csv)
    df_in["row_id"] = df_in["row_id"].astype(str)
    if args.limit:
        df_in = df_in.head(args.limit)

    # 断点续传
    scores_path = out_dir / "llm_signal_scores.parquet"
    existing = pd.DataFrame()
    if scores_path.exists():
        existing = pd.read_parquet(scores_path)
        existing["row_id"] = existing["row_id"].astype(str)
        done = set(existing["row_id"])
        df_remain = df_in[~df_in["row_id"].isin(done)].copy()
        print(f"断点续传: 已 {len(existing)} 条, 剩 {len(df_remain)} 条")
    else:
        df_remain = df_in.copy()

    client = OpenAI(api_key=api_key, base_url=args.api_base)

    if len(df_remain) > 0:
        print(f"\n开始 LLM 标注: {len(df_remain)} 条 · 并发 {args.concurrency} · 模型 {args.model}")
        print(f"成本估算 ≈ ${len(df_remain) * 0.0004:.2f}\n")
        results = []
        lock = threading.Lock()
        start = time.time()

        def task(row):
            return annotate_one(client, row, system_prompt, signal_ids, args.model)

        rows = df_remain.to_dict("records")
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(task, r): r for r in rows}
            completed = 0
            for fut in as_completed(futures):
                r = fut.result()
                with lock:
                    results.append(r)
                    completed += 1
                    if completed % 20 == 0:
                        elapsed = time.time() - start
                        eta = elapsed / completed * (len(rows) - completed)
                        err = sum(1 for x in results if x.get("_error"))
                        print(f"  {completed}/{len(rows)} · {elapsed:.0f}s · ETA {eta:.0f}s · err {err}")
                    if completed % args.checkpoint_every == 0:
                        snap = pd.concat([existing, pd.DataFrame(results)], ignore_index=True)
                        snap.to_parquet(scores_path, index=False)
                        print(f"  ✓ checkpoint → {scores_path.name} ({len(snap)} rows)")

        final = pd.concat([existing, pd.DataFrame(results)], ignore_index=True)
    else:
        final = existing

    final.to_parquet(scores_path, index=False)
    err_count = final["_error"].notna().sum() if "_error" in final.columns else 0
    print(f"\n→ {scores_path}  ({len(final)} rows, {err_count} errors)")

    # 按 segment_label 聚合 → segment_pricing_summary.csv (Phase 2 直接读)
    merged = final.merge(df_in[["row_id", "segment_label", "source"]],
                         on="row_id", how="left")
    merged = merged.dropna(subset=["segment_label"])

    seg = (merged.groupby(["source", "segment_label"])[signal_ids]
           .mean().reset_index())
    seg["n_reviews"] = (merged.groupby(["source", "segment_label"])["row_id"]
                       .count().values)
    seg["segment_share"] = seg["n_reviews"] / seg["n_reviews"].sum()
    seg = seg.rename(columns={"segment_label": "segment"})

    cols = ["source", "segment", "n_reviews", "segment_share"] + signal_ids
    seg = seg[cols]
    seg.to_csv(out_dir / "segment_pricing_summary.csv", index=False)
    print(f"→ {out_dir / 'segment_pricing_summary.csv'}  ({len(seg)} segments × {len(signal_ids)} signals)")

    # 信号活跃度报告
    print(f"\n=== 17 信号活跃度（LLM 评论 ≥ 1 分的比例）===")
    for sig in signal_ids:
        rate = (final[sig] >= 1).mean()
        bar = "█" * int(rate * 50)
        print(f"  {sig:40s} {rate:5.1%}  {bar}")


if __name__ == "__main__":
    main()
