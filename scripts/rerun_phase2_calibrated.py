"""
用 LLM 校准后的 β 重跑 Phase 2，对比 v1 prior vs v2 calibrated 的 P(buy) 差异。

Output:
  price_scenario_conversion_v2.csv
  before_after_comparison.csv
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--phase0-summary", required=True)
    p.add_argument("--phase1-signals", required=True)
    p.add_argument("--config-v1", required=True, help="v1 prior config")
    p.add_argument("--config-v2", required=True, help="v2 calibrated config")
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    summary = json.loads(Path(args.phase0_summary).read_text())
    anchor_3pack = summary["combined_range"]["mid"] if "combined_range" in summary else summary["combined_range_v1"]["mid"]
    anchor_unit = anchor_3pack / 3

    seg = pd.read_csv(args.phase1_signals)
    cfg_v1 = json.loads(Path(args.config_v1).read_text())
    cfg_v2 = json.loads(Path(args.config_v2).read_text())

    def compute(config_label, config):
        rows = []
        for _, r in seg.iterrows():
            for price, lab in zip(config["price_points_for_simulation"],
                                  config["price_point_labels"]):
                price_term = config["price_elasticity"] * np.log(price / anchor_unit)
                signal_term = sum(sig_def["beta"] * r.get(sig_id, 0)
                                   for sig_id, sig_def in config["signals"].items())
                logit_mid = config["base_logit"] + price_term + signal_term
                rows.append({
                    "version": config_label,
                    "segment": r["llm_label_k20"] if "llm_label_k20" in r.index else r.get("segment", ""),
                    "n_reviews": int(r["n_reviews"]),
                    "segment_share": float(r["segment_share"]),
                    "price_label": lab,
                    "price_per_unit": price,
                    "p_buy_mid": float(sigmoid(logit_mid)),
                })
        return pd.DataFrame(rows)

    v1_df = compute("v1_prior", cfg_v1)
    v2_df = compute("v2_calibrated", cfg_v2)
    both = pd.concat([v1_df, v2_df], ignore_index=True)
    both.to_csv(out_dir / "price_scenario_conversion_v2.csv", index=False)
    print(f"→ {out_dir / 'price_scenario_conversion_v2.csv'}")

    # 全市场加权 P(buy) 对比
    summary_compare = (both.assign(w=lambda d: d.p_buy_mid * d.segment_share)
                       .groupby(["version", "price_label", "price_per_unit"])
                       .agg(market_p_buy=("w", "sum"))
                       .reset_index()
                       .sort_values(["price_per_unit", "version"]))

    pivot = summary_compare.pivot(index="price_label", columns="version", values="market_p_buy")
    pivot["delta_pp"] = (pivot["v2_calibrated"] - pivot["v1_prior"]) * 100
    pivot["delta_pct"] = (pivot["v2_calibrated"] - pivot["v1_prior"]) / pivot["v1_prior"] * 100
    pivot.to_csv(out_dir / "before_after_comparison.csv")
    print(f"→ {out_dir / 'before_after_comparison.csv'}")
    print("\n=== 全市场加权 P(buy) 对比 ===")
    print(pivot.to_string(
        formatters={"v1_prior": "{:.2%}".format,
                    "v2_calibrated": "{:.2%}".format,
                    "delta_pp": "{:+.2f}pp".format,
                    "delta_pct": "{:+.1f}%".format}))


if __name__ == "__main__":
    main()
