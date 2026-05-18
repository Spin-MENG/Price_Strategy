# 方法 1 · 竞品规格回归（Hedonic Regression）

## 目的

把「市场上类似产品按 spec 该卖多少钱」量化出来。

## 模型

```
log(price_3pack_equiv) = β₀ + Σ β_i · spec_feature_i + ε
```

为什么用 log-log：
- 价格右偏 → log 让残差更接近正态
- spec → price 是乘法（speed 翻倍 → 价格约 ×2）→ log-log 才正确捕捉

## 输入

- spec_matrix CSV（≥ 8 行，最好 12-15 行）
- 哪些字段进回归由 `config.spec_features[].in_hedonic = true` 决定

## 输出

```json
{
  "r2": 0.946,
  "adj_r2": 0.882,
  "n": 12,
  "coefs": {"const": -0.31, "phy_total_mbps": 1.07, ...},
  "p_values": {"phy_total_mbps": 0.011, ...},
  "own_pred": 194,
  "own_pi_low": 128,
  "own_pi_high": 296
}
```

## 何时失效

| 症状 | 原因 | 修复 |
|---|---|---|
| R² < 0.5 | spec 异质性太高 | 减少特征数 / 剔除离群品 |
| 关键系数 p > 0.10 | 样本太小 | WebSearch 拉更多竞品到 ≥ 12 |
| 系数符号反直觉 | 多共线性 | 把 wifi_gen + has_6ghz 之类的成对特征二选一 |

## 调参建议（按品类）

- 控制变量数 ≤ n/2（n=12 → 最多 6 个特征）
- 对量级大的数值字段（速率、容量、功率）取 log
- 二值特征不取 log
- 高端品牌 dummy（如 is_premium_brand）通常显著 + 价值正向

## 业务读法

把系数翻译成「每多 1 单位特征，价格涨多少 %」：
```
价格涨幅 % = (exp(β) - 1) × 100
```
log 字段是「特征翻倍带来的涨幅」。

例（WiFi Mesh Router）：
- `phy_total_mbps` β = +1.07 → 总速率翻倍，价格 +191%（最强驱动）
- `is_premium_brand` β = +0.17 → 高端品牌名值 +18.7%（不显著但方向对）

## 报告里怎么呈现

HTML 报告 Section 2 「方法一详情 · 哪些规格最影响价格」横向柱图：
- 横轴：价格变动 %
- 纵轴：spec 特征（用业务语言：「总速率（每翻倍）」「高端品牌名」等）
- 颜色：显著 = 深色 / 不显著 = 浅色
- 不出现「β」「p-value」「log-log」字样
