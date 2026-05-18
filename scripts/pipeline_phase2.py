"""
Phase 2 价格情景模拟（通用版 Bayesian-flavored logit）。

输入：
  --phase0-summary  Phase 0 summary.json（含三法中位 → ANCHOR）
  --phase1-signals  Phase 1 segment_pricing_summary.csv
  --config          品类配置（含 β 表）
  --output-dir      落盘

输出：
  price_scenario_conversion.csv   N 分群 × 4 价格点 P(buy)
  pricing_model_params.json       β + ANCHOR
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_config(path: str) -> dict:
    return json.loads(Path(path).read_text())


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase0-summary", required=True)
    p.add_argument("--phase1-signals", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = load_config(args.config)
    summary = json.loads(Path(args.phase0_summary).read_text())

    anchor_3pack = summary["combined_range"]["mid"]
    anchor_unit = anchor_3pack / 3  # convention: 3-pack equivalent

    base_logit = config.get("base_logit", -2.20)
    price_points = config["price_points_for_simulation"]
    price_labels = config["price_point_labels"]
    signals = config["signals"]

    seg = pd.read_csv(args.phase1_signals)
    print(f"载入 {len(seg)} 个 segments")
    print(f"ANCHOR per unit: {anchor_unit:.0f} {config['currency']}")

    rows = []
    for _, r in seg.iterrows():
        for price, lab in zip(price_points, price_labels):
            price_term = config["price_elasticity"] * np.log(price / anchor_unit)
            signal_term = sum(sig_def["beta"] * r.get(sig_id, 0)
                              for sig_id, sig_def in signals.items())
            logit_mid = base_logit + price_term + signal_term

            n = max(r["n_reviews"], 5)
            signal_var = sum((sig_def["beta"] * 0.3) ** 2 for sig_def in signals.values())
            se = np.sqrt(signal_var / n + 0.4 ** 2)

            rows.append({
                "source": r["source"],
                "segment": r["segment"],
                "n_reviews": int(r["n_reviews"]),
                "segment_share": float(r["segment_share"]),
                "price_label": lab,
                "price_per_unit": price,
                "price_3pack_equiv": price * 3,
                "p_buy_low":  float(sigmoid(logit_mid - 1.96 * se)),
                "p_buy_mid":  float(sigmoid(logit_mid)),
                "p_buy_high": float(sigmoid(logit_mid + 1.96 * se)),
                "uncertainty_se": float(se),
            })

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "price_scenario_conversion.csv", index=False)
    print(f"→ {out_dir / 'price_scenario_conversion.csv'} ({len(df)} rows)")

    # 全市场加权
    print("\n=== 各价位 全市场加权 P(buy_mid) ===")
    market = (df.assign(w=lambda d: d.p_buy_mid * d.segment_share)
              .groupby(["price_label", "price_per_unit"])
              .agg(p_buy_weighted=("w", "sum"))
              .reset_index().sort_values("price_per_unit"))
    print(market.to_string(index=False,
        formatters={"p_buy_weighted": "{:.2%}".format}))

    params = {
        "version": "pipeline-v1",
        "anchor_unit_currency": config["currency"],
        "anchor_unit": float(anchor_unit),
        "anchor_3pack": float(anchor_3pack),
        "base_logit": base_logit,
        "price_elasticity": config["price_elasticity"],
        "signals_beta": {k: v["beta"] for k, v in signals.items()},
        "price_points": price_points,
        "calibration_status": "v1_baseline_pending_phase4_real_sales_posterior",
    }
    (out_dir / "pricing_model_params.json").write_text(json.dumps(params, ensure_ascii=False, indent=2))
    print(f"→ {out_dir / 'pricing_model_params.json'}")


if __name__ == "__main__":
    main()
