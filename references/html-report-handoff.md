# HTML 报告生成 · 调用 data-team-skills:html-report

## 角色分工

| Skill | 负责 |
|---|---|
| `pricing-pipeline` | 跑数据、产出 CSV/JSON 中间结果 + ECharts 数据 |
| `data-team-skills:html-report` | 把上述结果按 GL.iNet 模板渲染成 HTML |

## 调用流程

### Step 1 · pricing-pipeline 完成 Phase 0-2 + 0.5

跑完后 `pricing_outputs/` 里有：
- `summary.json`
- `pain_weighted.csv`
- `segment_pricing_summary.csv`
- `price_scenario_conversion.csv`
- `pricing_model_params.json`
- `market_gap_matrix.csv`
- `market_gap_top10.csv`

### Step 2 · 准备 7 个章节的内容 dict

```python
{
  "title": "<品类> 定价综合报告 v1 · 数据驱动的价格-缺口决策",
  "subtitle": "<日期>",
  "audience": "product_management_executive",  # 强制业务语言
  "currency": config["currency"],
  "meta_cells": [
    {"label": "报告期", "value": "2026-05-18"},
    {"label": "数据源", "value": "竞品评论 N=... · Reddit N=... · 12 款竞品规格"},
    {"label": "货币", "value": "EUR（欧元）"},
    {"label": "撰写", "value": "Data Team"},
  ],
  "sections": [...]
}
```

### Step 3 · 7 个章节模板

#### Section 1 · 一页全景

```python
{
  "label": "一页全景",
  "h2": "<主标题，含 ANCHOR 价 + 核心 SKU>",
  "desc": "<3 句话 TL;DR>",
  "kpi_cards": [
    {"label":"主力定价", "value":"€73 / 节点", "sub":"PPT $80 USD ≈ €73", "highlight":True},
    {"label":"市场购买意愿", "value":"38%", "sub":"@ €73 价位"},
    {"label":"价格敏感度", "value":"低", "sub":"涨到 €90 只跌 7pp"},
    {"label":"最大市场空缺", "value":"中价位", "sub":"€150-220 mesh 稳定性", "warn":True},
  ],
  "insights": [
    {"strong":"核心三句：", "body":"<3 条核心结论>"},
    {"warning":True, "strong":"需注意：", "body":"<不确定性提示>"},
  ]
}
```

#### Section 2 · 分析一 · 竞品对位（4 个 KPI + 3 张子图）

```python
{
  "label": "分析一 · 竞品对位",
  "h2": "竞品规格能撑住多少钱：三种方法独立计算",
  "kpi_cards": [
    {"label":"方法 1 · 规格驱动", "value":"€194 / 3-pack", "sub":"..."},
    {"label":"方法 2 · 性价比前沿", "value":"€220 / 3-pack", "sub":"同档 Deco BE25"},
    {"label":"方法 3 · 痛点加权",   "value":"€200 / 3-pack", "sub":"竞品 +4.1%"},
    {"label":"三法中位（基准）",     "value":"€205 / 3-pack", "highlight":True, "sub":"≈ €68 / 节点"},
  ],
  "charts": [
    {"id":"chart-three-methods",   "type":"h-bar",    "data":<methods×price>, "title":"三种方法的定价对比"},
    {"id":"chart-spec-impact",     "type":"h-bar",    "data":<hedonic coef>, "title":"方法一详情 · 哪些规格最影响价格"},
    {"id":"chart-perf-price-map",  "type":"scatter",  "data":<pareto pts>, "title":"方法二详情 · 性价比座标图"},
    {"id":"chart-top-pains",       "type":"h-bar",    "data":<top 15 pains>, "title":"方法三详情 · 用户最常抱怨的 15 件事"},
  ],
  "tables": [{"title":"用户痛点贡献明细 · 前 5", "data":<pain_weighted.csv top 5>}]
}
```

#### Section 3 · 分析二 · 谁会买（17 信号 + 分群表）
#### Section 4 · 分析三 · 价格情景（柱图 + 曲线）
#### Section 5 · 分析四 · 市场空缺（缺口柱图 + 价位竞品表）
#### Section 6 · 定价决策（3 轨 SKU 矩阵）
#### Section 7 · 上市路线图（结论 + 行动 + 术语表）

→ 完整模板参考 MeshNode 定价综合报告 v1 的 7 个 section 结构。

## 业务语言转换表（强制）

| 技术术语 | 报告里改成 |
|---|---|
| Hedonic regression | 规格驱动定价 / 按 spec 拟合 |
| Pareto frontier | 性价比前沿 / 性能-价格座标 |
| β / beta | 权重 / 武器 / 拉力（按上下文）|
| Logit / sigmoid | 概率模型推算 |
| P(buy) | 购买意愿率 / 会购买的概率 |
| Bayesian | 概率框架（一般不提）|
| ANCHOR | 基准价 |
| Phase 0 / 1 / 2 / 0.5 | 分析一 / 二 / 三 / 四 |
| TCO | 3 年使用成本 |
| Elasticity | 价格敏感度 |
| Cluster / persona / segment | 用户分群 |
| Posterior | 真实销售校准 / 数据反推 |
| F1 / Cohen's κ | 一致性检查 / 准确率 |
| Cluster-aggregated proxy | 分群聚合 |
| Gap_score | 机会分数 |

## 调用方式（Claude 在 pipeline 完成后）

```
Skill: data-team-skills:html-report
args:
  title: "MeshNode 定价综合报告 v1 · 数据驱动的价格-缺口决策"
  sections_json: <7 个章节的 dict 序列化>
  output_path: <工作目录>/<品类>_定价综合报告.html
  audience: product_management_executive
```

html-report skill 会拿这些 dict 渲染到 GL.iNet 黄昏绮景模板。

## 失败处理

| 症状 | 修复 |
|---|---|
| 章节 6/7 没渲染 | template.html 默认 5 个 nth-child border-top；超过 5 章节自动加 gold/orange/coral |
| ECharts 不显示 | 确认 chart_id 唯一；data 数组类型正确 |
| 业务语言里冒出技术词 | 查上面的转换表，逐条改 |
