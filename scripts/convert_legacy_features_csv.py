"""
把旧版 features.csv（含 price_3pack_eur 字段）转换成 pricing-pipeline 期望的
spec_matrix.csv 格式（含 price_per_unit + currency + market + pack_size）。

旧版常见于 MeshNode 项目和早期定价分析中。

用法：
  python convert_legacy_features_csv.py \
    --input <legacy features.csv> \
    --output <spec_matrix.csv> \
    --currency EUR \
    --market DE
"""

import argparse
from pathlib import Path

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--currency", default="EUR")
    p.add_argument("--market", default="DE")
    p.add_argument("--pack-size", type=int, default=1,
                   help="如果数据是 3-pack 套，给 3；single 给 1")
    args = p.parse_args()

    df = pd.read_csv(args.input)

    if "price_3pack_eur" in df.columns:
        df["price_per_unit"] = df["price_3pack_eur"] / 3
        df["pack_size"] = 1   # 转换后是 single 单价
    elif "price_3pack" in df.columns:
        df["price_per_unit"] = df["price_3pack"] / 3
        df["pack_size"] = 1
    elif "price_per_unit" in df.columns:
        df["pack_size"] = df.get("pack_size", args.pack_size)
    else:
        raise SystemExit("无 price_3pack_eur / price_3pack / price_per_unit 字段")

    df["currency"] = args.currency
    df["market"] = args.market

    # 必需字段在前
    front = ["brand", "model", "price_per_unit", "currency", "market", "pack_size"]
    rest = [c for c in df.columns if c not in front]
    df = df[front + rest]

    df.to_csv(args.output, index=False)
    print(f"→ {args.output}  ({len(df)} rows, currency={args.currency}, market={args.market})")


if __name__ == "__main__":
    main()
