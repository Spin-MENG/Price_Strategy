"""
把 raw 评论 corpus（parquet / CSV）转成 pricing-pipeline 期望的标准 reviews CSV。

输入格式：任何含 review-level 文本字段的 parquet / CSV
输出格式（必需列）：
  row_id, text, title, persona, segment_label, source

用法：
  # competitor reviews (来自 customer-persona-clustering 的 v1/clusters.parquet)
  python prep_reviews_csv.py \
    --input ../personas+pain-points-4q/output/variants/v1/clusters.parquet \
    --output reviews.csv \
    --text-col text --title-col title --persona-col persona \
    --segment-col llm_label_k20 --id-col reviewId \
    --source competitor \
    --min-text-len 30

  # 追加 Reddit reviews
  python prep_reviews_csv.py \
    --input reddit_corpus.csv \
    --output reviews.csv --append \
    --text-col body --segment-col flair --source reddit
"""

import argparse
from pathlib import Path

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="parquet or CSV")
    p.add_argument("--output", required=True)
    p.add_argument("--append", action="store_true",
                   help="追加到现有 CSV（去重 row_id）")
    p.add_argument("--text-col", default="text")
    p.add_argument("--title-col", default="title")
    p.add_argument("--persona-col", default="persona")
    p.add_argument("--segment-col", required=True,
                   help="用于按 segment 聚合的列名（如 llm_label_k20）")
    p.add_argument("--id-col", default=None,
                   help="行 ID 列；不指定则用 source_{row_index}")
    p.add_argument("--source", required=True, help="competitor / reddit / etc.")
    p.add_argument("--min-text-len", type=int, default=30,
                   help="text 短于这个长度的过滤掉")
    args = p.parse_args()

    inp = Path(args.input)
    if inp.suffix == ".parquet":
        df = pd.read_parquet(inp)
    else:
        df = pd.read_csv(inp)

    # 必需列校验
    if args.text_col not in df.columns:
        raise SystemExit(f"缺 text 列：{args.text_col}")
    if args.segment_col not in df.columns:
        raise SystemExit(f"缺 segment 列：{args.segment_col}")

    df = df[df[args.text_col].notna()]
    df = df[df[args.text_col].astype(str).str.len() >= args.min_text_len]

    out = pd.DataFrame()
    if args.id_col and args.id_col in df.columns:
        out["row_id"] = df[args.id_col].astype(str)
    else:
        out["row_id"] = [f"{args.source}_{i+1}" for i in range(len(df))]
    out["text"] = df[args.text_col].astype(str)
    out["title"] = df[args.title_col].astype(str) if args.title_col in df.columns else ""
    out["persona"] = df[args.persona_col].astype(str) if args.persona_col in df.columns else ""
    out["segment_label"] = df[args.segment_col].astype(str)
    out["source"] = args.source

    # 去重 row_id
    out = out.drop_duplicates(subset=["row_id"], keep="first")

    out_path = Path(args.output)
    if args.append and out_path.exists():
        existing = pd.read_csv(out_path)
        combined = pd.concat([existing, out], ignore_index=True)
        combined = combined.drop_duplicates(subset=["row_id"], keep="first")
        combined.to_csv(out_path, index=False)
        print(f"→ {out_path}  追加: {len(out)} 新 · 合计 {len(combined)} · 去重后")
    else:
        out.to_csv(out_path, index=False)
        print(f"→ {out_path}  {len(out)} reviews · source={args.source} · segment_col={args.segment_col}")

    # segments 分布
    seg_counts = out["segment_label"].value_counts()
    print(f"  Segment 数: {seg_counts.shape[0]}")
    print(f"  Top 5: {seg_counts.head(5).to_dict()}")


if __name__ == "__main__":
    main()
