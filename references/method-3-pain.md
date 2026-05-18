# 方法 3 · 用户痛点加权（Pain-weighted）

## 目的

用户的痛能让本品加价（如果能解）或减价（如果踩雷）。

## 公式

```
total_adjustment_pct = Σ_cluster  rel_pct × max(|sat|, 0.5) × theme_weight × source_weight

pain_adjusted_price = hedonic_base × (1 + total_adjustment_pct)
```

变量定义：
| 符号 | 意义 |
|---|---|
| `rel_pct` | 该痛点 cluster 在评论中的提及率 |
| `sat` | 该痛点的用户满意度（负数 = 更痛）|
| `theme_weight` | 该痛点主题的权重（正 = 本品能解 → 加价；负 = 本品也踩 → 折让）|
| `source_weight` | Reddit 0.4 / Competitor 0.6（如果两源都给）；否则 1.0 |

## 权重定义（在 config）

`config.pain_to_solve_weight` 字典：
```json
{
  "subscription_paywall": 0.09,        // 本品解 → +9%/痛
  "stability_handoff":    0.06,
  "value_disappointment": -0.06,       // 价格敏感 → -6%/痛
  "own_brand_specific":  -0.10         // 本品也踩 → -10%/痛（防守）
}
```

## 数据流

```
痛点 HTML → extract_html_data.py → JSON
        → decode_pain_pages.py → decoded JSON (含 quadrant 数据)
        → pipeline_phase0.py 的 run_pain_weighted() → contribution per theme
```

## 报告呈现

HTML 报告 Section 2「方法三详情 · 用户最常抱怨的 N 件事」横向柱：
- 横轴：用户提及率 %
- 纵轴：痛点 cluster（按提及率从高到低）
- 颜色：
  - 绿色 = 本品能解（pain_to_solve_weight > 0）→ 支撑加价
  - 红色 = 价格敏感 / 本品踩 → 要求让价
  - 灰色 = 与定价无直接关联

## 业务读法

```
绿色加总 → 本品潜在加价空间
红色加总 → 本品价格让步空间
两者净额 → pain_adjusted_price - hedonic_base 的最终方向
```

## Reddit / Competitor 双源加权依据

| 源 | 权重 | 理由 |
|---|---|---|
| Competitor 评论 | 0.6 | 真实付款后反馈，更接近购买意图 |
| Reddit 讨论 | 0.4 | 技术派偏多，会高估极客痛点；但补充覆盖广 |

只有一个源时权重 1.0。

## 何时失效

| 症状 | 原因 | 修复 |
|---|---|---|
| 总调整接近 0% | 痛点 keyword 不命中 themes | 调 `pain_themes` 关键词更宽 |
| 总调整 > +10% | 痛点 weight 过激进 | 减权重；或排除 `own_brand_specific` 防守项 |
| Reddit 比 Competitor 拉得更高 | Reddit 偏极客 | 检查源加权比例，可调到 Reddit 0.3 / Comp 0.7 |
