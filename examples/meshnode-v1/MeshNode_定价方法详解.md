# WiFi Mesh 路由器 定价方法详解 v1

> **配套报告**：`wifi-mesh-router_定价综合报告.html`
> **撰写**：GL.iNet Data Team · 2026-05-18
> **目标读者**：定价决策方、PM、分析师
> **可独立交付**：是

---

## 0 · 方法全景

```
                        ┌──── 方法 1 · 竞品规格回归 ────┐
Phase 0 · 竞品锚定 ────┼──── 方法 2 · 性价比前沿对位 ──┼──→ 基准价
（三法）               └──── 方法 3 · 用户痛点加权 ────┘   (205 EUR / 3-pack)
                                                              │
Phase 0.5 · 第四法                                            │
痛点 × 价格白地分析 ───────────────────→ 缺口机会清单         │
                                                              │
Phase 1 · 信号抽取 ────→ 17 条 0/1/2 信号 × 18 个分群
                                                              ▼
Phase 2 · 价格情景 ────→ 概率模型 ──→ 购买意愿率(分群, 价格)
                                                              │
                              （上市后）                       │
Phase 4 · 真实销售校准 ←──── attach_rate / sales_volume ──────┘
                              用真实数据更新参数（跳过人工标注）
```

---

## 1 · Phase 0 · 三法

### 1.1 方法 1：竞品规格回归（Hedonic）

**目的**：把「什么 spec 配什么价」的市场规律拟合出来，反推本品的预测价。

**模型**：
```
log(price_3pack_equiv) = β₀ + Σ β_i · spec_feature_i + ε
```

**v1 结果**：
- R² = 0.946 / 调整 R² = 0.882
- 样本 n = 12
- 本品预测：194 EUR（95% PI [128, 296]）

### 1.2 方法 2：性价比前沿对位（Pareto）

**目的**：在「性能 × 价格」坐标系上找最有效率的产品，看本品该落在哪。

**v1 结果**：
- 本品性能综合分 = -0.123
- 前沿对位价 = **220 EUR**

### 1.3 方法 3：痛点加权（Pain-weighted）

**公式**：
```
total_adjustment_pct = Σ_cluster  rel_pct × max(|sat|, 0.5) × weight
```

**v1 结果**：
- 净调整：+3.23%
- 痛点调整后价：201 EUR

### 1.4 三法综合

- min 194  /  mid **205**  /  max 220  → ANCHOR = 205 EUR

---

## 2 · Phase 0.5 · 第四法（市场缺口分析）

`gap_score = pain_density × meshnode_solve × under_served_factor`

→ 完整 top 15 缺口见 `pricing_outputs/market_gap_top10.csv`

---

## 3 · Phase 1 · 信号抽取（17 条）

数据粒度：cluster-aggregated proxy（persona × pain_cluster rate_matrix）。
信号尺度：cap 0.6 匹配 v0 review-aggregated 典型上限。

详见 `pricing_outputs/segment_pricing_summary.csv`

---

## 4 · 校准策略（不走人工标注）

v1 baseline **不做** Phase 1.5 人工标注。校准走：

- **主**：上市后真实销售 posterior 更新（无需人工，无成本）
- **辅**：LLM 自动代理标注（可选 · $15-25 · 3 小时跑完）

---

## 5 · Phase 2 · 概率模型公式

```
logit(seg, price) = base_logit
                  + β_price × log(price / ANCHOR)
                  + Σ β_signal × score(seg, signal)
P(buy) = sigmoid(logit)
```

**v1 参数**：
- base_logit = -2.2
- 价格弹性 = -1.5
- 17 个信号 β 权重见 `pricing_outputs/pricing_model_params.json`

---

## 6 · 心理价格红线

| 红线 | 来源 | 值 |
|---|---|---|
| 单件 hard cap | 用户心理上限 | **100** EUR |
| 套餐预算 anchor | 多件总价心理预算 | **400** EUR |
| 总价 anger zone | 触发愤怒退货的总价 | **500** EUR |

---

## 7 · 文件清单

```
pricing_outputs/
├── summary.json                  Phase 0 三法 + ANCHOR
├── pain_weighted.csv             痛点贡献明细
├── segment_pricing_summary.csv   Phase 1 信号 × 分群
├── price_scenario_conversion.csv Phase 2 价格情景 P(buy)
├── pricing_model_params.json     模型参数 + β
├── market_gap_matrix.csv         Phase 0.5 全矩阵
└── market_gap_top10.csv          Top 缺口 + SKU 推荐
```

---

## 8 · 复用 checklist（应用到新品类）

| 步骤 | 替换什么 | 复用什么 |
|---|---|---|
| 品类配置 | `references/default-configs/<new>.json` | schema |
| 痛点主题 | `pain_themes` + 关键词 | 框架 |
| 信号定义 | `signals` + β 权重 | logit 公式 |
| 校准 | 上市后真实销售 posterior | 无需人工 |

---

## 9 · 不确定性

| # | 不确定性 | 缓解 |
|---|---|---|
| 1 | β 全为经验值 | Phase 4 真实销售校准 |
| 2 | cluster-aggregated 不等于 review-level | Phase 4 真实 attach 反推 |
| 3 | 品牌归因稀疏（无关键词的 cluster 摊到所有 band） | C band 结论最硬 |
| 4 | 无 conjoint / 真实购买数据 | Phase 4 必做 |
| 5 | 跳过 Phase 1.5 人工校准 | sensitivity analysis：低置信信号 β ±50% 看 SKU 排序是否稳健 |

---

*GL.iNet Data Team · 2026-05-18 · v1 baseline · 可独立交付*
