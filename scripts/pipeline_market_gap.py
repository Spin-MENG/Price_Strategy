"""
Phase 0.5 第四法 · 痛点 × 价格缺口分析（通用版）。

输入：
  --pain-data       竞品痛点 decoded
  --reddit-pain     可选 · Reddit 痛点
  --config          品类配置
  --output-dir      落盘

输出：
  market_gap_matrix.csv     band × theme 密度矩阵
  market_gap_top10.csv      top 15 缺口 + SKU 推荐
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def to_band(price: float, bands: list) -> str:
    for b in bands:
        if b["min"] <= price < b["max"]:
            return f"{b['id']} · {b['label']}"
    return f"{bands[-1]['id']} · {bands[-1]['label']}"


def find_brand_mentions(text: str, brand_kw: dict) -> dict:
    counts = {}
    for brand, kws in brand_kw.items():
        for kw in kws:
            n = text.count(kw)
            if n > 0:
                counts[brand] = counts.get(brand, 0) + n
    return counts


def assign_theme(name: str, samples: list, themes: dict) -> str | None:
    text = name + " " + " ".join(samples or [])
    for theme_id, theme_def in themes.items():
        if any(kw in text for kw in theme_def.get("keywords", [])):
            return theme_id
    return None


def collect_clusters(source_name: str, decoded: dict,
                     variant_key: str, k_key: str) -> tuple[list, list]:
    if not decoded:
        return [], []
    var = decoded.get("variants", {}).get(variant_key)
    if not var:
        var = next(iter(decoded.get("variants", {}).values()), None)
    if not var:
        return [], []
    payload = var.get("k_to_payload", {}).get(k_key) or next(iter(var.get("k_to_payload", {}).values()), None)
    if not payload:
        return [], []

    pains, positives = [], []
    for q in payload.get("quadrant", []):
        rec = {
            "source": source_name,
            "cluster_name": q.get("name", ""),
            "samples": q.get("samples", []),
            "relevance_pct": float(q.get("relevance_pct", 0)),
            "satisfaction": float(q.get("satisfaction", 0)),
            "n_phrases": int(q.get("n_phrases", 0)),
        }
        if q.get("type") == "pain":
            pains.append(rec)
        elif q.get("type") == "positive":
            positives.append(rec)
    return pains, positives


def attribute_and_score(clusters: list[dict], config: dict) -> pd.DataFrame:
    themes = config["pain_themes"]
    brand_kw = config["brand_keywords"]
    brand_prices = config["brand_price_per_unit_eur"]
    bands = config["price_bands"]

    rows = []
    for c in clusters:
        text = c["cluster_name"] + " " + " ".join(c["samples"])
        brand_hits = find_brand_mentions(text, brand_kw)
        theme = assign_theme(c["cluster_name"], c["samples"], themes)
        if not theme:
            continue
        strength = c["relevance_pct"] * max(abs(c["satisfaction"]), 0.5)

        if brand_hits:
            total = sum(brand_hits.values())
            for brand, hits in brand_hits.items():
                share = hits / total
                price = brand_prices.get(brand)
                if price is None:
                    continue
                band = to_band(price, bands)
                rows.append({
                    "source": c["source"], "cluster": c["cluster_name"],
                    "theme": theme, "brand": brand,
                    "price_per_unit": price, "band": band,
                    "brand_share_in_cluster": share,
                    "strength": strength * share,
                    "relevance_pct": c["relevance_pct"],
                    "satisfaction": c["satisfaction"],
                })
        else:
            # 无品牌归因 → 平均分到所有 band 作 baseline
            for b in bands:
                rows.append({
                    "source": c["source"], "cluster": c["cluster_name"],
                    "theme": theme, "brand": "(all-brand)",
                    "price_per_unit": None,
                    "band": f"{b['id']} · {b['label']}",
                    "brand_share_in_cluster": 1 / len(bands),
                    "strength": strength / len(bands),
                    "relevance_pct": c["relevance_pct"],
                    "satisfaction": c["satisfaction"],
                })
    return pd.DataFrame(rows)


def recommend_sku(row, sku_template: dict) -> str:
    band = row["band"]
    theme = row["theme"]
    if band.startswith("A"):
        return f"{sku_template['attack']['label_zh']} {sku_template['attack']['pack_size']}-pack 攻击价"
    if band.startswith("B"):
        return f"{sku_template['core']['label_zh']} 单件 + 套装"
    if band.startswith("C"):
        return f"{sku_template['core']['label_zh']} / {sku_template['premium']['label_zh']} - 撕中价位"
    if band.startswith("D"):
        return "(不主攻 — brand-locked 用户)"
    return "(不参战 — spec 攻不上去)"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pain-data", required=True)
    p.add_argument("--reddit-pain")
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--competitor-variant", default="v1",
                   help="只取竞品痛点的这个 variant (默认 v1)")
    p.add_argument("--competitor-k", default="8",
                   help="只取竞品痛点的这个 k-level (默认 8)")
    p.add_argument("--reddit-variant", default="v2",
                   help="只取 Reddit 痛点的这个 variant (默认 v2 = strategic 层)")
    p.add_argument("--reddit-k", default="5",
                   help="只取 Reddit 痛点的这个 k-level (默认 5 = 最稳定切刀)")
    p.add_argument("--multi-k", action="store_true",
                   help="如要聚合多个 k-level（会膨胀 gap_score），传此 flag")
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)

    pain_clusters, pos_clusters = [], []

    if args.multi_k:
        sources = [("Competitor", args.pain_data, ["v0", "v1"], ["5", "8"])]
        if args.reddit_pain:
            sources.append(("Reddit", args.reddit_pain, ["v2", "v1", "v0"], ["5", "10"]))
    else:
        # 默认：每源只取一个 (variant, k)，避免同一 cluster 多 K-level 重复累加导致 gap_score 膨胀
        sources = [("Competitor", args.pain_data, [args.competitor_variant], [args.competitor_k])]
        if args.reddit_pain:
            sources.append(("Reddit", args.reddit_pain, [args.reddit_variant], [args.reddit_k]))

    for src_name, path, variants, ks in sources:
        decoded = json.loads(Path(path).read_text())
        for v in variants:
            for k in ks:
                pains, pos = collect_clusters(src_name + f"_{v}k{k}", decoded, v, k)
                pain_clusters.extend(pains)
                pos_clusters.extend(pos)
    print(f"收集 {len(pain_clusters)} 痛点 cluster + {len(pos_clusters)} 正面 cluster")

    df = attribute_and_score(pain_clusters, config)
    print(f"\n品牌归因后 {len(df)} 条 cluster × brand 记录")

    matrix = (df.groupby(["band", "theme"])
              .agg(pain_density=("strength", "sum"),
                   n_evidence=("cluster", "count"),
                   avg_relevance_pct=("relevance_pct", "mean"),
                   worst_satisfaction=("satisfaction", "min"))
              .reset_index())

    pos_df = attribute_and_score(pos_clusters, config) if pos_clusters else pd.DataFrame()
    if not pos_df.empty:
        pos_sum = pos_df.groupby("band").agg(best_pos_sat=("satisfaction", "max")).reset_index()
        matrix = matrix.merge(pos_sum, on="band", how="left")
    else:
        matrix["best_pos_sat"] = 0
    matrix["best_pos_sat"] = matrix["best_pos_sat"].fillna(0)
    matrix["under_served_factor"] = 1 - matrix["best_pos_sat"] / 2.0
    matrix["meshnode_solve"] = matrix["theme"].map(config["meshnode_solve"]).fillna(0)
    matrix["gap_score"] = matrix["pain_density"] * matrix["meshnode_solve"] * matrix["under_served_factor"]

    matrix = matrix.sort_values(["band", "gap_score"], ascending=[True, False])
    matrix.to_csv(out_dir / "market_gap_matrix.csv", index=False)
    print(f"→ {out_dir / 'market_gap_matrix.csv'}")

    sku_template = config["sku_track_template"]
    top = matrix.sort_values("gap_score", ascending=False).head(15).copy()
    top["recommended_sku"] = top.apply(lambda r: recommend_sku(r, sku_template), axis=1)
    top.to_csv(out_dir / "market_gap_top10.csv", index=False)
    print(f"→ {out_dir / 'market_gap_top10.csv'}")

    print(f"\n=== Top 10 缺口（按 gap_score 排序）===")
    cols = ["band", "theme", "pain_density", "meshnode_solve", "gap_score", "recommended_sku"]
    print(top[cols].head(10).to_string(
        index=False,
        formatters={"pain_density": "{:5.2f}".format,
                    "meshnode_solve": "{:.2f}".format,
                    "gap_score": "{:5.2f}".format}))


if __name__ == "__main__":
    main()
