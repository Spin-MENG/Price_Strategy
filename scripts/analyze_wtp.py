"""
WTP 分析 v3 · unit-aware：把单节点 WTP 和套装 WTP 分开看，剔除 ISP / PC / 其他噪声。

v3 vs v2:
  · 按 wtp_unit_type (v3 新增字段) 严格分类
  · single_router / 2/3/5_pack / bundle_unknown_pack → 保留，归一到单节点
  · monthly_isp_fee / monthly_subscription / pc_parts / other → 剔除（默认不入分布）
  · 输出 wtp_per_node.csv (单节点) + wtp_bundle.csv (套装总价) 两条分布
  · 旧 wtp_summary.csv / wtp_anchors.csv 保留为 legacy 全量视图（不剔除）

输入: llm_signal_scores.parquet + reviews.csv (segment_label)
输出:
  wtp_per_node.csv       单节点 WTP 分布（推荐和 PPT 单节点价对比）
  wtp_bundle.csv         套装 WTP 分布（推荐和 PPT 套装价对比）
  wtp_clean_anchors.csv  剔除 ISP / PC / 其他后的锚点（带 per_node_eur 归一列）
  wtp_summary.csv        [legacy] 全量 segment × sentiment 聚合（未剔除）
  wtp_anchors.csv        [legacy] 全量锚点
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import numpy as np


# 与 pipeline_phase1_llm.py 的 WTP_UNIT_TYPES 保持一致
ROUTER_UNIT_KEEP = {"single_router", "2_pack", "3_pack", "5_pack", "bundle_unknown_pack"}
DIVISOR = {"single_router": 1, "2_pack": 2, "3_pack": 3, "5_pack": 5,
           "bundle_unknown_pack": 3}  # bundle 未明示时按 3-pack 估算
DROP_UNIT = {"monthly_isp_fee", "monthly_subscription", "pc_parts", "other"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scores", required=True,
                   help="LLM 标注 parquet（含 wtp_unit_type 列，v3+）")
    p.add_argument("--reviews", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--ppt-price-eur", type=float, default=73.0,
                   help="本品 PPT 单节点价（用于单节点分位对比）")
    p.add_argument("--ppt-bundle-eur", type=float, default=None,
                   help="本品 PPT 套装总价（不指定则用 ppt-price-eur × 3）")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    ppt_node = args.ppt_price_eur
    ppt_bundle = args.ppt_bundle_eur if args.ppt_bundle_eur is not None else ppt_node * 3

    df = pd.read_parquet(args.scores)
    df["row_id"] = df["row_id"].astype(str)
    rev = pd.read_csv(args.reviews)
    rev["row_id"] = rev["row_id"].astype(str)
    df = df.merge(rev[["row_id", "segment_label", "source"]], on="row_id", how="left")

    has_unit_type = "wtp_unit_type" in df.columns
    if not has_unit_type:
        print("⚠ wtp_unit_type 列不存在 → 退回 v2 legacy 行为（不做粒度分类）")
        print("  建议: 用 v3+ pipeline_phase1_llm.py 重跑标注")
        df["wtp_unit_type"] = None

    n_total = len(df)
    n_mentioned = int(df["wtp_mentioned"].sum())
    n_value = int(df["wtp_value_eur"].notna().sum())

    print(f"\n=== WTP 全量统计（含噪声）===")
    print(f"  样本: {n_total}")
    print(f"  提到价格: {n_mentioned} ({n_mentioned/n_total:.1%})")
    print(f"  抽出 EUR 数字: {n_value} ({n_value/n_total:.1%})")

    # unit_type 分布
    if has_unit_type and n_value:
        ut_counts = df[df["wtp_value_eur"].notna()]["wtp_unit_type"].fillna("(null)").value_counts()
        print(f"\n=== wtp_unit_type 分布（{n_value} 条带 EUR 值的评论）===")
        for ut, n in ut_counts.items():
            tag = "✓ keep" if ut in ROUTER_UNIT_KEEP else ("✗ drop" if ut in DROP_UNIT else "? null")
            print(f"  {ut:24s} {n:>5}  {tag}")


    # ============ Per-Node WTP（归一到单节点）============
    df_keep = df[df["wtp_unit_type"].isin(ROUTER_UNIT_KEEP) &
                 df["wtp_value_eur"].between(5, 5000)].copy()
    df_keep["per_node_eur"] = df_keep.apply(
        lambda r: r["wtp_value_eur"] / DIVISOR[r["wtp_unit_type"]], axis=1)
    per_node = df_keep[df_keep["per_node_eur"].between(10, 600)].copy()
    bundle = df_keep[df_keep["wtp_value_eur"].between(50, 2000)].copy()

    print(f"\n=== Per-Node WTP (单节点 / 归一后) ===")
    pn = per_node["per_node_eur"]
    if len(pn):
        print(f"  n = {len(pn)}")
        print(f"  中位 €{pn.median():.0f} · IQR [€{pn.quantile(.25):.0f}, €{pn.quantile(.75):.0f}]")
        print(f"  mean ± std: €{pn.mean():.0f} ± €{pn.std():.0f}")
        print(f"  range: [€{pn.min():.0f}, €{pn.max():.0f}]")
        print(f"  PPT €{ppt_node:.0f} 落在 {((pn <= ppt_node).mean())*100:.0f}% 分位")
    else:
        print("  n = 0  (no router-related single-node anchors)")

    # Per-Node sentiment
    print(f"\n  Per-Node 各 sentiment 中位:")
    pn_sent_stats = {}
    for sent in ["anchor", "ceiling", "floor", "fair", "complaint"]:
        sub = per_node[per_node.wtp_sentiment == sent]
        if len(sub):
            med = sub["per_node_eur"].median()
            pn_sent_stats[sent] = {"n": int(len(sub)), "median": float(med),
                                    "p25": float(sub["per_node_eur"].quantile(.25)),
                                    "p75": float(sub["per_node_eur"].quantile(.75))}
            print(f"    {sent:10s}  n={len(sub):3d}  中位 €{med:.0f}")


    # ============ Bundle WTP（套装总价）============
    print(f"\n=== Bundle WTP (套装总价) ===")
    b = bundle["wtp_value_eur"]
    if len(b):
        print(f"  n = {len(b)}")
        print(f"  中位 €{b.median():.0f} · IQR [€{b.quantile(.25):.0f}, €{b.quantile(.75):.0f}]")
        print(f"  PPT 套装 €{ppt_bundle:.0f} 落在 {((b <= ppt_bundle).mean())*100:.0f}% 分位")
    print(f"\n  pack_size 拆解:")
    for u in ["single_router", "2_pack", "3_pack", "5_pack", "bundle_unknown_pack"]:
        sub = df_keep[df_keep["wtp_unit_type"] == u]
        if len(sub):
            if u == "single_router":
                print(f"    {u:22s}  n={len(sub):3d}  中位 €{sub['wtp_value_eur'].median():.0f}")
            else:
                print(f"    {u:22s}  n={len(sub):3d}  bundle 中位 €{sub['wtp_value_eur'].median():.0f}"
                      f"  → per-node €{sub['per_node_eur'].median():.0f}")


    # ============ 输出 CSV ============
    # 1. per-node 分布
    per_node_out = per_node[[
        "row_id", "segment_label", "source", "wtp_value_eur", "per_node_eur",
        "wtp_sentiment", "wtp_unit_type", "wtp_context"]].sort_values("per_node_eur")
    per_node_out.to_csv(out_dir / "wtp_per_node.csv", index=False)
    print(f"\n→ {out_dir/'wtp_per_node.csv'}  ({len(per_node_out)} 条单节点 WTP)")

    # 2. bundle 分布
    bundle_out = bundle[[
        "row_id", "segment_label", "source", "wtp_value_eur", "per_node_eur",
        "wtp_sentiment", "wtp_unit_type", "wtp_context"]].sort_values("wtp_value_eur")
    bundle_out.to_csv(out_dir / "wtp_bundle.csv", index=False)
    print(f"→ {out_dir/'wtp_bundle.csv'}  ({len(bundle_out)} 条套装 WTP)")

    # 3. 清洗后锚点
    clean = df_keep[[
        "row_id", "segment_label", "source", "wtp_value_eur", "per_node_eur",
        "wtp_sentiment", "wtp_unit_type", "wtp_context"]].sort_values("per_node_eur")
    clean.to_csv(out_dir / "wtp_clean_anchors.csv", index=False)
    print(f"→ {out_dir/'wtp_clean_anchors.csv'}  ({len(clean)} 条 router-related 锚点)")

    # 4. [Legacy] 全量 wtp_summary.csv (segment × sentiment, 不剔除)
    seg_summary = []
    for seg, sub in df.groupby("segment_label"):
        wtp_sub = sub[sub.wtp_value_eur.between(10, 2000)]
        seg_summary.append({
            "segment": seg,
            "n_reviews": len(sub),
            "n_wtp_mentioned": int(sub["wtp_mentioned"].sum()),
            "wtp_rate": float(sub["wtp_mentioned"].mean()),
            "wtp_value_count": len(wtp_sub),
            "wtp_median_eur": float(wtp_sub["wtp_value_eur"].median()) if len(wtp_sub) else None,
            "wtp_p25_eur": float(wtp_sub["wtp_value_eur"].quantile(.25)) if len(wtp_sub) else None,
            "wtp_p75_eur": float(wtp_sub["wtp_value_eur"].quantile(.75)) if len(wtp_sub) else None,
            "ceiling_count": int((sub.wtp_sentiment == "ceiling").sum()),
            "floor_count":   int((sub.wtp_sentiment == "floor").sum()),
            "anchor_count":  int((sub.wtp_sentiment == "anchor").sum()),
            "fair_count":    int((sub.wtp_sentiment == "fair").sum()),
        })
    ssum = pd.DataFrame(seg_summary).sort_values("n_reviews", ascending=False)
    ssum.to_csv(out_dir / "wtp_summary.csv", index=False)
    print(f"→ {out_dir/'wtp_summary.csv'}  [legacy 全量 · {len(ssum)} segments]")

    # 5. [Legacy] 全量锚点
    anchors_legacy = df[df.wtp_value_eur.notna()].copy()
    anchors_legacy = anchors_legacy[anchors_legacy.wtp_value_eur.between(10, 2000)]
    keep_cols = ["row_id", "segment_label", "source", "wtp_value_eur",
                 "wtp_sentiment", "wtp_context"]
    if "wtp_unit_type" in anchors_legacy.columns:
        keep_cols.insert(-1, "wtp_unit_type")
    anchors_legacy[keep_cols].sort_values("wtp_value_eur").to_csv(
        out_dir / "wtp_anchors.csv", index=False)
    print(f"→ {out_dir/'wtp_anchors.csv'}  [legacy 全量 · {len(anchors_legacy)} 锚点]")


    # ============ PPT sanity check ============
    print(f"\n=== PPT sanity check ===")
    if len(pn):
        ceiling_below = ((per_node.wtp_sentiment == "ceiling") &
                          (per_node["per_node_eur"] < ppt_node)).sum()
        floor_above = ((per_node.wtp_sentiment == "floor") &
                        (per_node["per_node_eur"] > ppt_node)).sum()
        verdict = ("OK" if ceiling_below <= floor_above * 2
                   else f"偏贵 - {ceiling_below} ceiling 在 PPT €{ppt_node} 之下")
        print(f"  单节点 PPT €{ppt_node}: ceiling<PPT = {ceiling_below}  ·  floor>PPT = {floor_above}  → {verdict}")
    if len(b):
        b_below = (b < ppt_bundle).sum()
        b_pct = (b <= ppt_bundle).mean() * 100
        print(f"  套装 PPT €{ppt_bundle}: {b_below}/{len(b)} 套装锚点 ≤ PPT  ({b_pct:.0f}% 分位)")


if __name__ == "__main__":
    main()
