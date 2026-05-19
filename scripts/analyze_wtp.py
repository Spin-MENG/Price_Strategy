"""
B 方案 · WTP 分析：从 LLM 标注的 4 个字段算分群级愿付分布。

输入: llm_BC_scores.parquet + reviews.csv (segment_label)
输出:
  wtp_summary.csv         按 (segment × wtp_sentiment) 聚合
  wtp_anchors.csv         所有 wtp_value_eur 锚点 + context（人工 review 用）
"""

import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scores", required=True)
    p.add_argument("--reviews", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--ppt-price-eur", type=float, default=73.0, help="本品 PPT 单节点价")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(args.scores)
    df["row_id"] = df["row_id"].astype(str)
    rev = pd.read_csv(args.reviews)
    rev["row_id"] = rev["row_id"].astype(str)
    df = df.merge(rev[["row_id","segment_label","source"]], on="row_id", how="left")

    n_total = len(df)
    n_mentioned = int(df["wtp_mentioned"].sum())
    n_value = int(df["wtp_value_eur"].notna().sum())

    print(f"=== B · WTP 全量统计 ===")
    print(f"  样本数: {n_total}")
    print(f"  提到价格的评论: {n_mentioned} ({n_mentioned/n_total:.1%})")
    print(f"  能抽出具体 EUR 数字的: {n_value} ({n_value/n_total:.1%})")

    # WTP 数字分布（去掉极端离群）
    wtp_v = df["wtp_value_eur"].dropna()
    wtp_v = wtp_v[(wtp_v >= 10) & (wtp_v <= 2000)]
    if len(wtp_v) > 0:
        print(f"\n  WTP 数字分布（EUR）:")
        print(f"    n = {len(wtp_v)}")
        print(f"    中位 {wtp_v.median():.0f} · IQR [{wtp_v.quantile(0.25):.0f}, {wtp_v.quantile(0.75):.0f}]")
        print(f"    mean ± std: {wtp_v.mean():.0f} ± {wtp_v.std():.0f}")
        print(f"    range: [{wtp_v.min():.0f}, {wtp_v.max():.0f}]")
        print(f"    PPT €{args.ppt_price_eur} 在分布的: {(wtp_v <= args.ppt_price_eur).mean():.1%} 分位")

    # 按 sentiment 分组
    print(f"\n  按 sentiment 分布:")
    sentiment_counts = df["wtp_sentiment"].fillna("none").value_counts()
    print(sentiment_counts.to_string())

    # 各 sentiment 的价格分布
    print(f"\n  各 sentiment 的中位 WTP（EUR）:")
    for sent in ["anchor", "ceiling", "floor", "fair"]:
        sub = df[(df.wtp_sentiment == sent) & df.wtp_value_eur.notna()]
        sub = sub[(sub.wtp_value_eur >= 10) & (sub.wtp_value_eur <= 2000)]
        if len(sub) > 0:
            print(f"    {sent:10s}  n={len(sub):3d}  中位 €{sub['wtp_value_eur'].median():.0f}  范围 [{sub['wtp_value_eur'].min():.0f}, {sub['wtp_value_eur'].max():.0f}]")

    # 输出 1: 分群级 WTP 摘要
    seg_summary = []
    for seg, sub in df.groupby("segment_label"):
        wtp_sub = sub[(sub.wtp_value_eur >= 10) & (sub.wtp_value_eur <= 2000)]
        seg_summary.append({
            "segment": seg,
            "n_reviews": len(sub),
            "n_wtp_mentioned": int(sub["wtp_mentioned"].sum()),
            "wtp_rate": float(sub["wtp_mentioned"].mean()),
            "wtp_value_count": len(wtp_sub),
            "wtp_median_eur": float(wtp_sub["wtp_value_eur"].median()) if len(wtp_sub) else None,
            "wtp_p25_eur": float(wtp_sub["wtp_value_eur"].quantile(0.25)) if len(wtp_sub) else None,
            "wtp_p75_eur": float(wtp_sub["wtp_value_eur"].quantile(0.75)) if len(wtp_sub) else None,
            "ceiling_count": int((sub.wtp_sentiment == "ceiling").sum()),
            "floor_count":   int((sub.wtp_sentiment == "floor").sum()),
            "anchor_count":  int((sub.wtp_sentiment == "anchor").sum()),
            "fair_count":    int((sub.wtp_sentiment == "fair").sum()),
        })
    ssum = pd.DataFrame(seg_summary).sort_values("n_reviews", ascending=False)
    ssum.to_csv(out_dir / "wtp_summary.csv", index=False)
    print(f"\n→ {out_dir / 'wtp_summary.csv'}  ({len(ssum)} segments)")

    # 输出 2: 所有具体锚点
    anchors = df[df.wtp_value_eur.notna()].copy()
    anchors = anchors[(anchors.wtp_value_eur >= 10) & (anchors.wtp_value_eur <= 2000)]
    anchors_out = anchors[["row_id","segment_label","source","wtp_value_eur","wtp_sentiment","wtp_context"]]
    anchors_out = anchors_out.sort_values("wtp_value_eur")
    anchors_out.to_csv(out_dir / "wtp_anchors.csv", index=False)
    print(f"→ {out_dir / 'wtp_anchors.csv'}  ({len(anchors_out)} 条具体锚点)")

    # PPT sanity check
    ppt = args.ppt_price_eur
    ceiling_below = ((df.wtp_sentiment=="ceiling") & (df.wtp_value_eur < ppt)).sum()
    floor_above   = ((df.wtp_sentiment=="floor")   & (df.wtp_value_eur > ppt)).sum()
    print(f"\n=== PPT €{ppt} sanity check ===")
    print(f"  ceiling < PPT (超过 EUR{ppt} 不买): {ceiling_below} 条")
    print(f"  floor > PPT (值更多): {floor_above} 条")
    print(f"  → 价格合理性: {'OK' if ceiling_below <= floor_above*2 else '偏贵 - 多数 ceiling 在 PPT 之下'}")


if __name__ == "__main__":
    main()
