"""
Phase 0 三法（通用版）· Hedonic + Pareto + Pain-weighted。

输入：
  --spec-matrix         12-15 个竞品 spec CSV
  --pain-data           竞品痛点 decoded JSON
  --reddit-pain         可选 · Reddit 痛点 decoded JSON
  --own-product-spec    可选 · 本品 spec JSON 或 dict（不给则用 config.own_product_default_spec）
  --config              品类配置 JSON 路径
  --output-dir          落盘目录

输出：
  summary.json          Hedonic + Pareto + Pain 三个价格 + 三法中位
  pain_weighted.csv     痛点贡献明细
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def load_spec_matrix(path: str, config: dict) -> pd.DataFrame:
    df = pd.read_csv(path)
    # 必需字段
    required = {"brand", "model", "price_per_unit"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"spec_matrix.csv 缺字段: {missing}")
    # 把 price_per_unit × 3 算成 3-pack equivalent（如果是 single）
    if "pack_size" in df.columns:
        df["price_3pack_equiv"] = df.apply(
            lambda r: r["price_per_unit"] * (3 / r["pack_size"]) if r["pack_size"] > 0 else r["price_per_unit"] * 3,
            axis=1)
    else:
        df["price_3pack_equiv"] = df["price_per_unit"] * 3
    return df


# -------------------- 方法 1: Hedonic --------------------
def run_hedonic(df: pd.DataFrame, own_spec: dict, config: dict) -> dict:
    """log(price) ~ spec features. 返回 own_spec 的预测价 + 95% PI."""
    feats = [f for f in config["spec_features"] if f.get("in_hedonic")]
    feat_cols = [f["col"] for f in feats]

    # 填缺
    for col in feat_cols:
        if col not in df.columns:
            print(f"  ⚠ spec_matrix 缺列 {col}, 跳过")
            continue
        df[col] = df[col].fillna(df[col].median())

    y = np.log(df["price_3pack_equiv"])
    X = pd.DataFrame()
    for f in feats:
        col = f["col"]
        if col not in df.columns:
            continue
        v = df[col].astype(float)
        if f.get("log"):
            v = np.log(v.clip(lower=1))
        X[col] = v
    X = sm.add_constant(X)

    model = sm.OLS(y, X).fit()

    # own_spec 预测
    own_row = {"const": 1.0}
    for f in feats:
        col = f["col"]
        v = own_spec.get(col, df[col].median() if col in df.columns else 0)
        if f.get("log"):
            v = np.log(max(v, 1))
        own_row[col] = v
    pred_log = model.predict(pd.DataFrame([own_row]))[0]
    pred = float(np.exp(pred_log))
    resid_std = np.sqrt(model.mse_resid)
    lo = float(np.exp(pred_log - 1.96 * resid_std))
    hi = float(np.exp(pred_log + 1.96 * resid_std))

    return {
        "r2": float(model.rsquared),
        "adj_r2": float(model.rsquared_adj),
        "n": int(model.nobs),
        "coefs": {k: float(v) for k, v in model.params.items()},
        "p_values": {k: float(v) for k, v in model.pvalues.items()},
        "own_pred": pred,
        "own_pi_low": lo,
        "own_pi_high": hi,
    }


# -------------------- 方法 2: Pareto --------------------
def run_pareto(df: pd.DataFrame, own_spec: dict, config: dict) -> dict:
    feats = [f for f in config["spec_features"] if f.get("in_hedonic")]
    cols = [f["col"] for f in feats if f["col"] in df.columns]

    # z-score
    z = (df[cols] - df[cols].mean()) / df[cols].std()
    df["perf_score"] = z.mean(axis=1)

    fr = df[["brand", "model", "perf_score", "price_3pack_equiv"]].sort_values("price_3pack_equiv").reset_index(drop=True)
    is_p = np.zeros(len(fr), dtype=bool)
    best = -np.inf
    for i in range(len(fr)):
        if fr["perf_score"].iloc[i] > best:
            is_p[i] = True
            best = fr["perf_score"].iloc[i]
    fr["is_pareto"] = is_p

    # own_spec 的 perf_score
    own_z = sum((own_spec.get(c, df[c].median()) - df[c].mean()) / df[c].std() for c in cols) / len(cols)
    own_z = float(own_z)

    fr_only = fr[fr.is_pareto].sort_values("perf_score")
    if own_z <= fr_only["perf_score"].min():
        frontier_price = float(fr_only["price_3pack_equiv"].iloc[0])
    elif own_z >= fr_only["perf_score"].max():
        frontier_price = float(fr_only["price_3pack_equiv"].iloc[-1])
    else:
        frontier_price = float(np.interp(own_z, fr_only["perf_score"], fr_only["price_3pack_equiv"]))

    return {
        "own_perf_score": own_z,
        "frontier_implied_price": frontier_price,
        "pareto_points": fr[fr.is_pareto][["brand", "model", "perf_score", "price_3pack_equiv"]].to_dict("records"),
        "all_points": fr[["brand", "model", "perf_score", "price_3pack_equiv", "is_pareto"]].to_dict("records"),
    }


# -------------------- 方法 3: Pain-weighted --------------------
def assign_theme(name: str, samples: list, themes_config: dict) -> str | None:
    text = name + " " + " ".join(samples or [])
    for theme_id, theme_def in themes_config.items():
        for kw in theme_def["keywords"]:
            if kw in text:
                return theme_id
    return None


def run_pain_weighted(pain_data: dict, reddit_pain_data: dict | None,
                       hedonic_base: float, config: dict) -> dict:
    themes = config["pain_themes"]
    weights = config["pain_to_solve_weight"]

    rows = []

    def collect(source_label: str, decoded: dict, variant_key: str, k_key: str, weight: float):
        if not decoded or "variants" not in decoded:
            return
        var = decoded["variants"].get(variant_key) or next(iter(decoded["variants"].values()), None)
        if not var:
            return
        payload = var.get("k_to_payload", {}).get(k_key)
        if not payload:
            # fallback to any k available
            payload = next(iter(var.get("k_to_payload", {}).values()), None)
        if not payload:
            return
        for q in payload.get("quadrant", []):
            if q.get("type") != "pain":
                continue
            name = q.get("name", "")
            rel = float(q.get("relevance_pct", 0)) / 100
            sat = float(q.get("satisfaction", 0))
            samples = q.get("samples", [])
            theme = assign_theme(name, samples, themes)
            theme_weight = weights.get(theme, 0) if theme else 0
            strength = rel * max(abs(sat), 0.5)
            contrib = strength * theme_weight * weight
            rows.append({
                "source": source_label,
                "cluster": name,
                "relevance_pct": rel * 100,
                "satisfaction": sat,
                "theme": theme,
                "theme_weight": theme_weight,
                "strength": strength,
                "weighted_contribution_pct": contrib * 100,
                "n_phrases": q.get("n_phrases"),
            })

    competitor_weight = 0.6 if reddit_pain_data else 1.0
    reddit_weight = 0.4 if reddit_pain_data else 0.0

    collect("Competitor", pain_data,
            variant_key=list(pain_data.get("variants", {}).keys())[0] if pain_data else "v0",
            k_key="5", weight=competitor_weight)
    if reddit_pain_data:
        collect("Reddit", reddit_pain_data,
                variant_key="v2" if "v2" in reddit_pain_data.get("variants", {}) else "v0",
                k_key="5", weight=reddit_weight)

    df = pd.DataFrame(rows)
    total_adj_pct = df["weighted_contribution_pct"].sum() if not df.empty else 0
    pain_adjusted_price = hedonic_base * (1 + total_adj_pct / 100)

    return {
        "rows": df,
        "weighted_net_adjustment_pct": float(total_adj_pct),
        "pain_adjusted_price": float(pain_adjusted_price),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec-matrix", required=True)
    p.add_argument("--pain-data", required=True, help="competitor pain decoded JSON")
    p.add_argument("--reddit-pain", help="optional Reddit pain decoded JSON")
    p.add_argument("--own-product-spec", help="optional JSON dict; uses config default if not given")
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)

    df = load_spec_matrix(args.spec_matrix, config)
    print(f"载入 {len(df)} 个竞品（spec_matrix）")

    own_spec = config["own_product_default_spec"]
    if args.own_product_spec:
        own_spec = {**own_spec, **json.loads(Path(args.own_product_spec).read_text())}

    print("\n=== 方法 1 · Hedonic ===")
    hed = run_hedonic(df, own_spec, config)
    print(f"  R²={hed['r2']:.3f}  adj={hed['adj_r2']:.3f}  n={hed['n']}")
    print(f"  预测：{hed['own_pred']:.0f}  PI: [{hed['own_pi_low']:.0f}, {hed['own_pi_high']:.0f}]")

    print("\n=== 方法 2 · Pareto Frontier ===")
    par = run_pareto(df, own_spec, config)
    print(f"  perf={par['own_perf_score']:+.3f}  frontier_price={par['frontier_implied_price']:.0f}")

    print("\n=== 方法 3 · Pain-weighted ===")
    pain_data = json.loads(Path(args.pain_data).read_text())
    reddit_data = json.loads(Path(args.reddit_pain).read_text()) if args.reddit_pain else None
    pain = run_pain_weighted(pain_data, reddit_data, hed["own_pred"], config)
    pain["rows"].to_csv(out_dir / "pain_weighted.csv", index=False)
    print(f"  净调整: {pain['weighted_net_adjustment_pct']:+.2f}%")
    print(f"  调整后价: {pain['pain_adjusted_price']:.0f}")

    p_min = min(hed["own_pred"], par["frontier_implied_price"], pain["pain_adjusted_price"])
    p_max = max(hed["own_pred"], par["frontier_implied_price"], pain["pain_adjusted_price"])
    p_mid = (hed["own_pred"] + par["frontier_implied_price"] + pain["pain_adjusted_price"]) / 3
    print(f"\n=== 三法中位 ===  {p_mid:.0f}  区间 [{p_min:.0f}, {p_max:.0f}]")

    summary = {
        "version": "pipeline-v1",
        "currency": config["currency"],
        "hedonic": hed,
        "frontier": par,
        "pain": {
            "weighted_net_adjustment_pct": pain["weighted_net_adjustment_pct"],
            "pain_adjusted_price": pain["pain_adjusted_price"],
        },
        "combined_range": {"min": float(p_min), "mid": float(p_mid), "max": float(p_max)},
        "own_product_spec_used": own_spec,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n→ {out_dir / 'summary.json'}")
    print(f"→ {out_dir / 'pain_weighted.csv'}")


if __name__ == "__main__":
    main()
