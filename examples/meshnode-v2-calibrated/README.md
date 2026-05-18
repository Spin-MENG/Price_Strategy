# MeshNode v2 · LLM-Calibrated Example

用 DeepSeek API 对 MeshNode v1 模型做 LLM 自动代理标注校准的完整产物。

## 关键数字

- 全量标注：**3,392 条评论**（不是抽样），耗时 6 分钟，成本 < $2
- **9/17 信号 trustworthy**（r > 0.5），β 保持
- **1 信号 discard**：setup_friction（r=0.08）
- **3 新信号过度乐观**：subscription_aversion / wireless_backhaul_failure / no_subscription_value，β 折让 40-70%
- **全市场加权 P(buy) 下调 ~10pp**（主力价 €73：37.8% → 27.5%）
- **定价决策不变**：€73 主力 + €285 Flint+2 仍是最优；但 hero claim 要调整

## 文件

| 文件 | 用途 |
|---|---|
| 校准报告_v2.md | 完整校准方法 + 结论 |
| calibration_summary.csv | 17 信号 r + 等级 + β 修正 |
| pricing_model_params_v2_calibrated.json | 校准后完整 config |
| before_after_comparison.csv | 4 价位 P(buy) 前后对比 |
| price_scenario_conversion_v2.csv | 18 segments × 4 价位 P(buy) v1 vs v2 |

## 复用

```bash
# 1. 准备样本（每条评论 + segment 标签）
python sample_prep.py --raw-corpus your_clusters.parquet --output sample_full.csv

# 2. LLM 标注（DeepSeek，~10 分钟 < $2）
export DEEPSEEK_API_KEY=sk-xxx
python scripts/llm_annotate_deepseek.py \
  --input sample_full.csv --output llm_scores.parquet --concurrency 15

# 3. 校准 β
python scripts/compute_calibration.py \
  --llm-scores llm_scores.parquet \
  --sample-meta sample_full.csv \
  --prior-segments your_segment_summary.csv \
  --config your_category_config.json \
  --output-dir .

# 4. 重跑 Phase 2 + 对比
python scripts/rerun_phase2_calibrated.py \
  --phase0-summary summary.json \
  --phase1-signals segment_pricing_summary.csv \
  --config-v1 your_category_config.json \
  --config-v2 pricing_model_params_v2_calibrated.json \
  --output-dir .
```

校准时间：~25-30 分钟（比人工 N=200 标注的 2 周快 200 倍）。
