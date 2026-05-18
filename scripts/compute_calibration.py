"""
LLM 标注 → 校准 metric + 修正 β。

输入：
  llm_scores_full.parquet      （每条 review 的 17 个 LLM 信号分）
  原模型的 segment-level scores（v1 cluster-aggregated proxy + persona priors）

步骤：
  1. 把 LLM scores 按 segment_k20 / segment_v1 聚合（每 signal 取 mean）
  2. 对每 signal: 算 LLM_agg vs v1_prior 的 Pearson r
  3. 分级（trustworthy / grey / discard）+ 修正 β
  4. 写校准报告 + 新 β JSON

输出：
  calibration_summary.csv      （每 signal 的 r + 等级 + β_old / β_new）
  pricing_model_params_v2_calibrated.json
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


SIGNALS_17 = [
    "coverage_pain_score", "stability_pain_score", "iot_pain_score",
    "setup_friction_score", "glinet_lockin_score", "openwrt_control_score",
    "vpn_usecase_score", "brand_lockin_score", "value_positive_score",
    "price_complaint_score", "discount_dependency_score",
    "competitor_substitution_score", "subscription_aversion_score",
    "wireless_backhaul_failure_score", "defection_intent_score",
    "no_subscription_value_score", "pro_control_score",
]
# 12 原 v0 信号（有 cluster-aggregated prior 可比）
SIGNALS_12_LEGACY = [
    "coverage_pain_score", "stability_pain_score", "iot_pain_score",
    "setup_friction_score", "glinet_lockin_score", "openwrt_control_score",
    "vpn_usecase_score", "brand_lockin_score", "value_positive_score",
    "price_complaint_score", "discount_dependency_score",
    "competitor_substitution_score",
]
# 5 个新 v1 信号（无 prior 可比，校准靠 LLM 标注 base rate）
SIGNALS_5_NEW = [
    "subscription_aversion_score", "wireless_backhaul_failure_score",
    "defection_intent_score", "no_subscription_value_score", "pro_control_score",
]


def confidence_factor(r: float) -> tuple[str, float]:
    """返回 (等级, β_乘数)。"""
    if r >= 0.5:
        return "trustworthy", 1.0
    if r >= 0.3:
        return "grey", 0.7      # 灰色信号 β 折让 30%
    if r >= 0.1:
        return "weak", 0.4      # 弱信号 大幅折让
    return "discard", 0.0       # 完全无相关 → β = 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--llm-scores", required=True)
    p.add_argument("--sample-meta", required=True, help="sample_full.csv 包含 segment_k20")
    p.add_argument("--prior-segments", required=True, help="v1 segment_pricing_summary_v1.csv")
    p.add_argument("--config", required=True, help="wifi-mesh-router config JSON")
    p.add_argument("--output-dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir); out_dir.mkdir(parents=True, exist_ok=True)
    config = json.loads(Path(args.config).read_text())

    llm = pd.read_parquet(args.llm_scores) if args.llm_scores.endswith(".parquet") else pd.read_csv(args.llm_scores)
    meta = pd.read_csv(args.sample_meta)
    meta["row_id"] = meta["row_id"].astype(str)
    llm["row_id"] = llm["row_id"].astype(str)
    # 去掉 meta 中重复的 row_id（少量竞品评论 ID 重复）
    meta = meta.drop_duplicates(subset=["row_id"], keep="first")
    # 去掉 llm 中重复行（断点续传可能产生）
    llm = llm.drop_duplicates(subset=["row_id"], keep="last")
    # join via merge (more tolerant than set_index assign)
    llm = llm.merge(meta[["row_id", "segment_k20", "source"]], on="row_id", how="left")
    llm = llm.dropna(subset=["segment_k20"])
    print(f"LLM 标注: {len(llm)} 条, {llm['segment_k20'].nunique()} 个 k20 segments")

    # LLM segment-level mean
    llm_seg = llm.groupby("segment_k20")[[f"llm_{s}" for s in SIGNALS_17]].mean()
    print(f"LLM segment 聚合后: {len(llm_seg)} segments")

    # 原 v0 prior segment scores（含 12 个原信号；新 5 个信号在 v0 里不存在）
    prior = pd.read_csv(args.prior_segments)
    prior_key = "llm_label_k20" if "llm_label_k20" in prior.columns else prior.columns[0]
    # 只取 prior 里有的信号列（v0 文件只有 12 个原信号）
    available_in_prior = [s for s in SIGNALS_17 if s in prior.columns]
    prior_indexed = prior.set_index(prior_key)[available_in_prior]
    print(f"原 prior: {len(prior_indexed)} segments × {len(available_in_prior)} 信号")

    # join：v0 k=20 segment 与 LLM 标注的 segment_k20 直接匹配
    joined_segs = sorted(set(llm_seg.index) & set(prior_indexed.index))
    print(f"\n两边匹配的 segment: {len(joined_segs)} 个")

    rows = []
    for s in SIGNALS_17:
        llm_col = f"llm_{s}"
        beta_old = config["signals"][s]["beta"]
        llm_mean = float(llm[llm_col].mean())
        llm_pos_rate = float((llm[llm_col] >= 1).mean())

        if s in SIGNALS_12_LEGACY and s in available_in_prior and len(joined_segs) >= 5:
            # 12 原信号：算 segment-level Pearson
            x = llm_seg.loc[joined_segs, llm_col].values
            y = prior_indexed.loc[joined_segs, s].values
            r = np.corrcoef(x, y)[0, 1] if np.std(x) > 0 and np.std(y) > 0 else 0.0
            grade, mult = confidence_factor(r)
            unit = "segment_pearson"
            beta_new = beta_old * mult
        else:
            # 5 新信号：无 prior 可比 → 用 LLM positive rate 作 sanity check
            # 如果 LLM rate ≥ 5%（合理活跃）→ 保留原 β；< 1% → 该信号几乎没出现，β 折让 50%
            r = float("nan")
            if llm_pos_rate >= 0.05:
                grade = "active_no_prior"; mult = 1.0
            elif llm_pos_rate >= 0.01:
                grade = "rare_no_prior";   mult = 0.6
            else:
                grade = "very_rare_no_prior"; mult = 0.3
            unit = "no_prior_baseline"
            beta_new = beta_old * mult

        rows.append({
            "signal": s,
            "pearson_r": r if np.isfinite(r) else None,
            "unit": unit,
            "grade": grade,
            "beta_multiplier": mult,
            "beta_old": beta_old,
            "beta_new": beta_new,
            "llm_mean_score": llm_mean,
            "llm_positive_rate": llm_pos_rate,
            "n_samples_segment_agg": len(joined_segs) if unit == "segment_pearson" else len(llm),
        })

    summary = pd.DataFrame(rows).sort_values("pearson_r", ascending=False)
    summary.to_csv(out_dir / "calibration_summary.csv", index=False)
    print(f"\n→ {out_dir / 'calibration_summary.csv'}")
    print("\n=== 校准结果 ===")
    print(summary[["signal", "pearson_r", "grade", "beta_old", "beta_new", "llm_positive_rate"]].to_string(
        index=False,
        formatters={"pearson_r": "{:+.3f}".format,
                    "beta_old": "{:+.2f}".format,
                    "beta_new": "{:+.2f}".format,
                    "llm_positive_rate": "{:.1%}".format}))

    # 新 β JSON
    config_v2 = json.loads(json.dumps(config))   # deep copy
    for r_ in rows:
        config_v2["signals"][r_["signal"]]["beta"] = r_["beta_new"]
        config_v2["signals"][r_["signal"]]["calibration"] = {
            "pearson_r": r_["pearson_r"],
            "grade": r_["grade"],
            "beta_multiplier": r_["beta_multiplier"],
        }
    config_v2["calibration_status"] = "v2_llm_calibrated_3392_samples_deepseek-chat"
    (out_dir / "pricing_model_params_v2_calibrated.json").write_text(
        json.dumps(config_v2, ensure_ascii=False, indent=2))
    print(f"→ {out_dir / 'pricing_model_params_v2_calibrated.json'}")

    # 等级统计
    print(f"\n=== 信号等级分布 ===")
    print(summary["grade"].value_counts().to_string())


if __name__ == "__main__":
    main()
