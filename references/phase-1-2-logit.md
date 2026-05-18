# Phase 1 信号抽取 + Phase 2 价格情景模拟

## Phase 1 · 信号抽取

### 信号定义

每个品类在 config 里定义 12-17 个信号：
```json
"signals": {
  "coverage_pain_score":  {"beta": 1.20, "themes": ["coverage_dead_zone"]},
  "stability_pain_score": {"beta": 1.40, "themes": ["stability_handoff"]},
  ...
}
```

每个信号：
- `beta`：Phase 2 logit 权重（正 = 拉高购买意愿；负 = 压低）
- `themes`：该信号对应的痛点主题列表（在 `pain_themes` 里）

### 抽取方法（v1 cluster-aggregated proxy）

```
对每个 persona × 每个 pain_cluster：
  rate_pct = persona 评论中提到该痛点的 %
  对每个信号：
    如果该 cluster 命中信号的任意 theme → 该信号 += (rate_pct / 100) × 2
    否则 += 0

  叠加 persona 名称关键词 match (×0.25)
  cap 0.6（匹配 v0 review-aggregated 典型上限）
```

### 数据流

```
persona/pain decoded JSON →
  pipeline_phase1.py →
    segment_pricing_summary.csv  (N 个分群 × M 个信号 × n_reviews)
```

### 为什么不做 review-level

v1 接收的输入是预聚合的 persona × pain_cluster 矩阵，**没有 raw review text**。
要做 review-level keyword 必须先用 customer-persona-clustering / social-reviews-analyzer 把 raw 文本喂回来 — 多一步，不值得。

cluster-aggregated 是合理 trade-off：粗一点但能跑。

---

## Phase 1.5 · 校准（跳过）

v1 baseline **不做** N=200 人工标注。理由：
- 数据组人手成本高
- 上市后第一批订单的真实 attach 数据 > 人工标注的「先验估计」
- 标注质量也不见得高（17 信号 × 200 样本是繁琐工作）

替代：
- **主**：Phase 4 真实销售 posterior 校准
- **辅**：LLM 自动代理标注（可选，3 小时跑完，~$25）

报告里不要让管理层「等校准」— 直接用 v1 prior 上市。

---

## Phase 2 · 价格情景 logit

### 模型

```
logit(seg, price) = base_logit
                  + price_elasticity × log(price / ANCHOR_per_unit)
                  + Σ_signal  β_signal × score(seg, signal)

P(buy_mid) = sigmoid(logit_mid)

SE = sqrt(Σ (β × σ_signal)² / max(n, 5) + σ_α²)
P(buy_low / high) = sigmoid(logit_mid ± 1.96 × SE)
```

默认值（在 config）：
- `base_logit` = -2.20 → baseline P(buy) ≈ 10% at ANCHOR
- `price_elasticity` = -1.5 → log-log
- σ_signal = 0.3，σ_α = 0.4

### 输入

- `summary.json`（Phase 0 三法中位 → ANCHOR）
- `segment_pricing_summary.csv`（Phase 1 分群 × 信号）
- 品类 config（含 β 表 + 价格点列表）

### 输出

| 文件 | 内容 |
|---|---|
| `price_scenario_conversion.csv` | N 分群 × 4 价格点 P(buy_low/mid/high) |
| `pricing_model_params.json` | β + ANCHOR + 价格弹性 |

### 报告呈现

HTML Section 3「分析三 · 价格情景」：
- 4 价格点 × 全市场加权 P(buy) 柱图
- 3-5 大目标分群价格-购买意愿曲线
- 每个分群名用业务语言（不是 LLM 自动命名的拗口词）

### 何时数值不合理

| 症状 | 原因 | 修复 |
|---|---|---|
| 全市场 P(buy) > 80% | 信号尺度过大 / β 过大 | 检查 cap 是否在 0.6；或降 β 30% |
| 全市场 P(buy) < 5% | base_logit 过低 | 提升 base_logit 到 -1.5 |
| 价格弹性 |elasticity| < 0.3 | β 太强压制了价格效应 | 降 β 整体；或加大 price_elasticity |
| 高 P(buy) 分群跨价位都 > 90% | 该分群信号过密 | 检查该 persona 的 cluster-rate 是否异常高 |

---

## Phase 4 · 真实销售 posterior

上市后用真实数据更新 β：

```
posterior(seg, price) = prior_v1(seg, price)
                      + observed_sales(seg, price)
                          × attach_rate_by_segment
                          × node_count_distribution
                          × goodcloud_login_attribution  # 用 GoodCloud 标 segment 标签
```

**埋点必须在 launch 前做好**：
- checkout 页 segment 标签（按 landing 来源 + GoodCloud 状态推断）
- 订单 SKU 拆分到 attach 类别
- GoodCloud 登录 → 设备激活归因链路

跑 8-12 周后第一次 posterior 修正。
