"""
LLM 自动代理标注 · DeepSeek API 批量打分（全量）

对每条 review 按 17 信号定义给 0/1/2 分。断点续传 + 并发 + 进度保存。

Usage:
  export DEEPSEEK_API_KEY=sk-xxx
  python llm_annotate.py \
    --input sample_full.csv \
    --output llm_scores.parquet \
    --concurrency 10
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading

import pandas as pd
from openai import OpenAI


# 17 信号定义（与 pricing-pipeline wifi-mesh-router 配置对齐）
SIGNAL_DEFS = """
请按以下 17 个信号给每条评论打 0/1/2 分（0=无证据，1=弱证据，2=强证据）：

1. coverage_pain_score          — 用户抱怨 WiFi 覆盖差/盲区/信号弱
2. stability_pain_score          — 用户抱怨断线/掉线/不稳定/需要重启
3. iot_pain_score                — 智能家居设备（Zigbee/Matter/IoT）兼容性问题
4. setup_friction_score          — 设置/安装/App 配置过程困难
5. glinet_lockin_score           — 用户是 GL.iNet 老用户或粉丝
6. openwrt_control_score         — 用户使用或想要 OpenWrt / 自定义固件
7. vpn_usecase_score             — 用户提到 VPN / WireGuard / Tailscale 用例
8. brand_lockin_score            — 用户对特定品牌（华硕/eero/Orbi）有强黏性
9. value_positive_score          — 用户正面提到性价比 / 物超所值
10. price_complaint_score        — 用户抱怨价格太贵 / 性价比差
11. discount_dependency_score    — 用户只在打折/翻新/二手时才买
12. competitor_substitution_score — 用户提到要换/换成其他品牌
13. subscription_aversion_score  — 用户抱怨订阅墙 / 付费功能 (eero Plus / AVM Smart Home 等)
14. wireless_backhaul_failure_score — 抱怨 mesh 节点之间无线回程不稳/需要有线回程
15. defection_intent_score       — 明确表达"退货 / 不会再买 / 准备换牌"
16. no_subscription_value_score  — 用户正面提到"不收订阅"是优点
17. pro_control_score            — 用户想要 VLAN / QoS / 高级控制选项

每个信号必须给 0、1、或 2。不确定时给 0。
"""

SYSTEM_PROMPT = f"""你是 WiFi mesh 路由器市场评论分析专家。

任务：阅读每条用户评论，按 17 个信号定义给 0/1/2 分。

{SIGNAL_DEFS}

输出严格 JSON 格式，键名与信号名完全一致。例：
{{"coverage_pain_score": 1, "stability_pain_score": 2, "iot_pain_score": 0, ...}}

只输出 JSON，不要任何解释文字。"""


def annotate_one(client: OpenAI, row: dict) -> dict:
    """单条 review → 17 信号 0/1/2 分。"""
    text = str(row.get("text", "")).strip()[:1200]  # cap to control tokens
    title = str(row.get("title", "")).strip()
    persona = str(row.get("persona", "")).strip()[:300]

    user_msg = f"""评论标题: {title or '(无)'}

评论正文:
{text}

中文 persona 分析（参考）:
{persona or '(无)'}

按 17 信号给 0/1/2 分，输出 JSON。"""

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=600,
        )
        content = resp.choices[0].message.content
        scores = json.loads(content)
        # 校验 17 个 key 都在
        expected_keys = [
            "coverage_pain_score", "stability_pain_score", "iot_pain_score",
            "setup_friction_score", "glinet_lockin_score", "openwrt_control_score",
            "vpn_usecase_score", "brand_lockin_score", "value_positive_score",
            "price_complaint_score", "discount_dependency_score",
            "competitor_substitution_score", "subscription_aversion_score",
            "wireless_backhaul_failure_score", "defection_intent_score",
            "no_subscription_value_score", "pro_control_score",
        ]
        result = {"row_id": row["row_id"]}
        for k in expected_keys:
            v = scores.get(k, 0)
            try:
                v = int(v)
                if v not in (0, 1, 2):
                    v = max(0, min(2, v))
            except Exception:
                v = 0
            result[f"llm_{k}"] = v
        return result
    except Exception as e:
        # 失败 → 返回全 0 + 标记
        result = {"row_id": row["row_id"], "_error": str(e)[:120]}
        for k in [
            "coverage_pain_score", "stability_pain_score", "iot_pain_score",
            "setup_friction_score", "glinet_lockin_score", "openwrt_control_score",
            "vpn_usecase_score", "brand_lockin_score", "value_positive_score",
            "price_complaint_score", "discount_dependency_score",
            "competitor_substitution_score", "subscription_aversion_score",
            "wireless_backhaul_failure_score", "defection_intent_score",
            "no_subscription_value_score", "pro_control_score",
        ]:
            result[f"llm_{k}"] = 0
        return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--checkpoint-every", type=int, default=100)
    p.add_argument("--limit", type=int, default=0, help="0 = full, else first N")
    args = p.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("缺 DEEPSEEK_API_KEY")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1")

    df = pd.read_csv(args.input)
    if args.limit:
        df = df.head(args.limit)

    out_path = Path(args.output)
    # 断点续传
    existing = pd.DataFrame()
    if out_path.exists():
        existing = pd.read_parquet(out_path) if out_path.suffix == ".parquet" else pd.read_csv(out_path)
        done_ids = set(existing["row_id"].astype(str))
        df = df[~df["row_id"].astype(str).isin(done_ids)]
        print(f"断点续传: 已完成 {len(existing)} 条, 剩余 {len(df)} 条")

    if len(df) == 0:
        print("全部已完成")
        return

    print(f"开始标注 {len(df)} 条, 并发 {args.concurrency}, 模型 deepseek-chat ...")
    print(f"成本估算 ≈ ${len(df) * 0.0003:.2f}-${len(df) * 0.0006:.2f}")

    results = []
    lock = threading.Lock()
    start = time.time()

    def task(row_dict):
        return annotate_one(client, row_dict)

    rows = df.to_dict("records")
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
                    err_count = sum(1 for x in results if x.get("_error"))
                    print(f"  {completed}/{len(rows)} done · elapsed {elapsed:.0f}s · ETA {eta:.0f}s · errors {err_count}")
                # checkpoint
                if completed % args.checkpoint_every == 0:
                    snap = pd.concat([existing, pd.DataFrame(results)], ignore_index=True)
                    if out_path.suffix == ".parquet":
                        snap.to_parquet(out_path, index=False)
                    else:
                        snap.to_csv(out_path, index=False)
                    print(f"  ✓ checkpoint 写入 {out_path} ({len(snap)} rows)")

    final = pd.concat([existing, pd.DataFrame(results)], ignore_index=True)
    if out_path.suffix == ".parquet":
        final.to_parquet(out_path, index=False)
    else:
        final.to_csv(out_path, index=False)

    elapsed = time.time() - start
    err = sum(1 for x in results if x.get("_error"))
    print(f"\n→ {out_path}  ({len(final)} rows)")
    print(f"  总耗时 {elapsed:.0f}s · 失败 {err} 条 · 成功率 {100*(1-err/len(results)):.1f}%")


if __name__ == "__main__":
    main()
