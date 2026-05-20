"""
Pipeline Step 5.5 (可选) · Router-Relevance 过滤器。

为什么需要：
  原始抓取（Reddit / Discourse / 论坛）经常含大量无关品类讨论。例如 mesh router 项目
  抓「WiFi」、「mesh」相关关键词时，Reddit 抓到游戏 / 装机 / 二手 / 闲聊。
  这些 review 上跑 17 个 mesh-router signals 全部得 0 分，但 review 仍进
  segment 聚合分母 → 稀释信号活跃度（例 31% → 5%），市场 P(buy_weighted) 被低估。

定义 router-relevant：
  · source == 'amazon'（电商评论默认全是路由器购买后评价）
  · OR sum(N 个 LLM signal 分数) >= 1（至少命中一个 mesh-router 信号）

输入：
  --reviews-csv         原始 reviews CSV
  --scores              LLM 标注 parquet（pipeline_phase1_llm.py 产出）
  --config              品类配置 JSON（取 signals 列表）
  --output-dir          落盘
  --include-sources     默认 ['amazon']；用户可改

输出：
  reviews_router_relevant.csv             过滤后的 reviews（同列）
  scores_router_relevant.parquet          过滤后的 scores（同列）
  segment_pricing_summary_router.csv      过滤后重聚合的 segment × signals (Phase 2 可直接读)
  filter_report.json                      过滤统计

用法：
  在 Phase 2 (segment 聚合 + logit) 之前插入这一步。若不用 router-relevant 过滤，
  跳过这个脚本，Phase 2 直接读 phase1 输出即可（与历史行为兼容）。
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reviews-csv", required=True)
    p.add_argument("--scores", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--include-sources", nargs="*", default=["amazon"],
                   help="始终保留的 source 名（默认 amazon）；这些跳过信号检查")
    p.add_argument("--min-signal-sum", type=int, default=1,
                   help="非白名单 source 至少要满足 sum(signals) >= 此值")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.config).read_text())
    signal_ids = list(config["signals"].keys())

    rev = pd.read_csv(args.reviews_csv)
    rev["row_id"] = rev["row_id"].astype(str)
    sc = pd.read_parquet(args.scores)
    sc["row_id"] = sc["row_id"].astype(str)

    if "_error" in sc.columns:
        n_err = sc["_error"].notna().sum()
        if n_err:
            print(f"⚠ 标注 parquet 含 {n_err} 条 _error 记录 → 已剔除")
            sc = sc[sc["_error"].isna()].copy()

    # 校验 signal 列存在
    missing = [s for s in signal_ids if s not in sc.columns]
    if missing:
        raise SystemExit(f"标注 parquet 缺信号列: {missing[:5]} ... ")

    sc["signal_sum"] = sc[signal_ids].sum(axis=1)
    merged = rev.merge(sc[["row_id", "signal_sum"]], on="row_id", how="left")
    merged["signal_sum"] = merged["signal_sum"].fillna(0)

    include = set(args.include_sources)
    keep_mask = (merged["source"].isin(include)) | (merged["signal_sum"] >= args.min_signal_sum)
    merged["router_relevant"] = keep_mask

    n_total = len(merged)
    n_keep = int(keep_mask.sum())
    n_drop = n_total - n_keep

    print(f"=== Router-Relevance Filter ===")
    print(f"  规则: source ∈ {sorted(include)} OR signal_sum >= {args.min_signal_sum}")
    print(f"  样本: {n_total}")
    print(f"  保留: {n_keep} ({n_keep/n_total:.1%})")
    print(f"  剔除: {n_drop} ({n_drop/n_total:.1%})  （无关品类噪声）")

    print(f"\n  按 source 拆解:")
    for src, sub in merged.groupby("source"):
        n_s = len(sub); n_s_keep = int(sub["router_relevant"].sum())
        whitelist = "[whitelist]" if src in include else ""
        print(f"    {src:20s} {n_s_keep:>5}/{n_s:<5} kept ({n_s_keep/n_s:.0%}) {whitelist}")

    # 落盘
    keep_rev = merged[keep_mask][rev.columns.tolist()]
    keep_rev.to_csv(out_dir / "reviews_router_relevant.csv", index=False)
    print(f"\n→ {out_dir/'reviews_router_relevant.csv'}  ({len(keep_rev)} rows)")

    keep_ids = set(keep_rev["row_id"])
    keep_sc = sc[sc["row_id"].isin(keep_ids)].drop(columns=["signal_sum"])
    keep_sc.to_parquet(out_dir / "scores_router_relevant.parquet", index=False)
    print(f"→ {out_dir/'scores_router_relevant.parquet'}  ({len(keep_sc)} rows)")

    # 过滤后重聚合 segment_pricing_summary_router.csv → Phase 2 可直接消费
    merged_sc = keep_sc.merge(keep_rev[["row_id", "segment_label", "source"]],
                               on="row_id", how="left")
    merged_sc = merged_sc.dropna(subset=["segment_label"])
    seg = (merged_sc.groupby(["source", "segment_label"])[signal_ids]
           .mean().reset_index())
    seg["n_reviews"] = (merged_sc.groupby(["source", "segment_label"])["row_id"]
                        .count().values)
    seg["segment_share"] = seg["n_reviews"] / seg["n_reviews"].sum()
    seg = seg.rename(columns={"segment_label": "segment"})
    seg = seg[["source", "segment", "n_reviews", "segment_share"] + signal_ids]
    seg.to_csv(out_dir / "segment_pricing_summary_router.csv", index=False)
    print(f"→ {out_dir/'segment_pricing_summary_router.csv'}  ({len(seg)} segments)")

    # 报告
    by_src = {}
    for src, sub in merged.groupby("source"):
        by_src[src] = {"n_total": int(len(sub)), "n_keep": int(sub["router_relevant"].sum())}
    report = {
        "rule": {
            "include_sources": sorted(include),
            "min_signal_sum": args.min_signal_sum,
            "signals_used": signal_ids,
        },
        "n_total": n_total, "n_keep": n_keep, "n_drop": n_drop,
        "keep_pct": float(n_keep / n_total) if n_total else 0,
        "by_source": by_src,
    }
    (out_dir / "filter_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"→ {out_dir/'filter_report.json'}")


if __name__ == "__main__":
    main()
