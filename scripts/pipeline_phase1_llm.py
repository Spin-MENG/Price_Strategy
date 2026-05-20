"""
Phase 1 v3 · LLM 信号识别（默认主流程）

每条 review 用 LLM (DeepSeek 默认) 按 N 信号定义打 0/1/2 分，
按 segment 聚合 → segment_pricing_summary.csv，Phase 2 直接用。

vs v2:
  · WTP 抽取增加 wtp_unit_type 强制枚举字段，解决「单节点价 vs 全套价 vs ISP 月费」混合问题
  · 旧 wtp_value_eur 字段保留，下游 analyze_wtp.py 可按 unit_type 归一/过滤
vs 旧 phase1 (cluster-aggregated proxy):
  · review-level 精度而非 cluster-aggregated
  · 信号 ground truth，无需事后校准
  · 不依赖 keyword 匹配 (PAIN_KEYWORD_MAP / PERSONA_PRIORS)

输入:
  --reviews-csv     竞品 + (可选) Reddit reviews CSV (含 row_id/text/segment_label/source)
  --config          品类配置 JSON
  --output-dir      落盘目录

输出:
  llm_signal_scores.parquet           每 review × N 信号 + 5 WTP 字段（含 wtp_unit_type）
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


# WTP 粒度枚举（v3 新增）。analyze_wtp.py 按 unit_type 归一 / 过滤。
WTP_UNIT_TYPES = (
    "single_router",         # 单台路由器 / 单 mesh 节点
    "2_pack",                # 2 节点套装
    "3_pack",                # 3 节点套装（最常见 mesh）
    "5_pack",                # 5 节点套装
    "bundle_unknown_pack",   # 是路由器套装但未明示 pack size
    "monthly_isp_fee",       # 宽带 ISP 服务月费（"$50/mo for internet"）
    "monthly_subscription",  # 路由器订阅服务（eero Plus / HomeShield / AVM Smart Home）
    "pc_parts",              # PC / 装机配件（SSD / CPU / GPU / 机箱）
    "other",                 # 跟 mesh router 无关的其他消费品
)


def build_prompt(signals: dict, currency: str = "EUR") -> str:
    """从品类配置的 signals 字典构造 LLM 标注 prompt。

    v3: 同时抽 5 个 WTP 字段（在 v2 基础上增加 wtp_unit_type 强制枚举，解决
    单节点价 vs 全套价 vs ISP 月费 混合问题）。
    """
    bullet = []
    for i, (sig_id, sig_def) in enumerate(signals.items(), 1):
        desc = sig_def.get("description") or sig_def.get("label") or sig_id.replace("_score", "").replace("_", " ")
        bullet.append(f"{i}. {sig_id} — {desc}")

    return f"""任务 A · 按以下 {len(signals)} 个信号给每条评论打 0/1/2 分（0=无证据 / 1=弱 / 2=强）：

{chr(10).join(bullet)}

任务 B · 抽 WTP（愿付价格）5 个字段：
- wtp_mentioned: 0/1（评论是否明确提到任何价格数字）
- wtp_value_eur: null 或 一个数字（标准化到 {currency}；如非 {currency} 按汇率换算 — 1 USD=0.92 EUR, 1 GBP=1.18 EUR）
- wtp_sentiment: 字符串
  · "anchor"   — 提到外部替代品价（如 "switched to 75€ alternative"）
  · "ceiling"  — 心理上限（"wouldn't pay more than €100"）
  · "floor"    — 心理下限/觉得值更多（"worth at least €150"）
  · "fair"     — 觉得该价位合理
  · "complaint"— 嫌贵但没说具体数（此时 wtp_value_eur=null）
  · null       — 评论里完全没碰价格
- wtp_context: 30 字内原文节选（包含价格那句），null 如无
- wtp_unit_type: 字符串，**严格从下列枚举中选一个**（不可自创）：
  · "single_router"        — 单台路由器/单 mesh 节点的售价或愿付价（"$73 per node"、"se cambio por otro de 75e"）
  · "2_pack"               — 明确 2 台 / 2 节点套装价（"2-pack for $130"、"pack of 2"）
  · "3_pack"               — 明确 3 台 / 3 节点套装价（"3 pack for 170€"、"pack de 3"、"3-pack bundle"）
  · "5_pack"               — 明确 5 台套装价
  · "bundle_unknown_pack"  — 是路由器套装但未明示几台（"the bundle was £250"）
  · "monthly_isp_fee"      — 宽带 ISP 服务月费（"$50 a month for internet"、"$70/mo for 1gig"）
  · "monthly_subscription" — 路由器附加订阅（eero Plus / HomeShield / AVM Smart Home 等）
  · "pc_parts"             — PC / 装机配件 / SSD / CPU / GPU / 机箱 / 内存 等硬件
  · "other"                — 跟 mesh router 无关的其他价（游戏、消费品、二手电器、配件等）
  · null                   — wtp_mentioned=0 时
  注意：当用户说 "wifi 6e router with satellite for $90" 时是 single_router（路由器主体+卫星算一台）；
  说 "I pay $50 a month" 没说服务内容时按 monthly_isp_fee 处理（最常见上下文）。

输出严格 JSON，所有 N+5 字段必须出现。例：
{{"{list(signals.keys())[0]}": 0, ..., "wtp_mentioned": 1, "wtp_value_eur": 170,
  "wtp_sentiment": "fair", "wtp_context": "I got 3 pack for 170€", "wtp_unit_type": "3_pack"}}

只输出 JSON，不要解释。"""


def annotate_one(client: OpenAI, row: dict, system_prompt: str,
                  signal_ids: list, model: str) -> dict:
    """v3: 同时抽 17 信号 + 5 WTP 字段（含 wtp_unit_type 强制枚举）。"""
    text = str(row.get("text", "")).strip()[:1200]
    title = str(row.get("title", "")).strip()
    persona = str(row.get("persona", "")).strip()[:300]
    user_msg = f"""评论标题: {title or '(无)'}

评论正文:
{text}

中文 persona 分析（参考，可能为空）:
{persona or '(无)'}

按 N+5 字段输出 JSON。"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.1, max_tokens=900,
        )
        scores = json.loads(resp.choices[0].message.content)
        result = {"row_id": row["row_id"]}
        # 信号
        for sig in signal_ids:
            v = scores.get(sig, 0)
            try:
                v = int(v); v = max(0, min(2, v))
            except Exception:
                v = 0
            result[sig] = v
        # WTP 字段（v3: 5 个，含 unit_type）
        result["wtp_mentioned"] = int(scores.get("wtp_mentioned", 0) or 0)
        wtpv = scores.get("wtp_value_eur")
        try:
            result["wtp_value_eur"] = float(wtpv) if wtpv is not None and wtpv != "" else None
        except Exception:
            result["wtp_value_eur"] = None
        sent = scores.get("wtp_sentiment")
        result["wtp_sentiment"] = sent if sent in ("anchor", "ceiling", "floor", "fair", "complaint") else None
        ctx = scores.get("wtp_context")
        result["wtp_context"] = str(ctx) if ctx else None
        utype = scores.get("wtp_unit_type")
        result["wtp_unit_type"] = utype if utype in WTP_UNIT_TYPES else None
        return result
    except Exception as e:
        result = {"row_id": row["row_id"], "_error": str(e)[:120]}
        for sig in signal_ids:
            result[sig] = 0
        result.update({"wtp_mentioned": 0, "wtp_value_eur": None,
                       "wtp_sentiment": None, "wtp_context": None,
                       "wtp_unit_type": None})
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
    currency = config.get("currency", "EUR")
    system_prompt = "你是消费电子市场评论分析专家。任务：按信号定义打分 + 抽 WTP 价格锚点。\n\n" + build_prompt(signals, currency)

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
    print(f"\n=== {len(signal_ids)} 信号活跃度（LLM 评论 ≥ 1 分的比例）===")
    for sig in signal_ids:
        rate = (final[sig] >= 1).mean()
        bar = "█" * int(rate * 50)
        print(f"  {sig:40s} {rate:5.1%}  {bar}")

    # WTP unit_type 分布报告（v3 新增）
    if "wtp_unit_type" in final.columns:
        with_value = final[final["wtp_value_eur"].notna()]
        print(f"\n=== wtp_unit_type 分布（{len(with_value)} 条有 EUR 值的评论）===")
        ut_counts = with_value["wtp_unit_type"].fillna("(null)").value_counts()
        for ut, n in ut_counts.items():
            keep = "✓ keep" if ut in ("single_router","2_pack","3_pack","5_pack","bundle_unknown_pack") else "✗ drop"
            print(f"  {ut:24s} {n:>5}  {keep}")
        print("  → 下游 analyze_wtp.py 按 unit_type 归一到单节点 / 套装两条独立分布")


if __name__ == "__main__":
    main()
