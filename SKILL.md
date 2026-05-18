---
name: pricing-pipeline
description: 数据驱动定价分析流水线 · 4 个独立方法（竞品规格回归 / 性价比前沿 / 用户痛点加权 / 市场缺口扫描）+ 价格情景模拟（购买意愿率推算）+ 上市 SKU 决策。Input 最少只要 4-5 个竞品种子（品牌/型号/价格），自动 WebSearch 扩展到 15 个完整竞品；本品规格/定价可选；竞品用户画像/痛点 HTML 或 CSV 必需；Reddit / 公网讨论画像 / 痛点可选。Output 交付级 HTML 业务报告（调 data-team-skills:html-report）+ 方法详解 MD（给分析师）。每个品类只需换一份 category-config JSON。
**Trigger when**：用户提到「定价分析」「pricing strategy」「价格情景」「市场缺口」「定价综合报告」「竞品对位定价」「价格-购买意愿曲线」，或显式 /pricing-pipeline；用户给一份竞品价格清单 + 用户画像/痛点要做定价决策；用户复用 MeshNode 那套四方法到新品类（KVM 切换器 / 智能水壶 / 任何消费电子）。
**Skip when**：纯销售数据分析（用 BI 工具）；纯成本/利润核算（用财务模型）；只问「这个产品该卖多少」但没提供竞品 + 用户数据（先让用户准备数据）。
---

# Pricing Pipeline · 数据驱动定价分析流水线

## 这个 skill 解决什么问题

给一个**新产品（或已定 PPT 价的产品）做端到端定价决策**，回答：
1. 按 spec 拟合，该产品该卖多少？（**方法一 · Hedonic**）
2. 在「性能 × 价格」前沿上，落在哪里合理？（**方法二 · Pareto**）
3. 用户的痛点能让我多收 / 少收多少钱？（**方法三 · 痛点加权**）
4. 在「价位段 × 痛点」二维坐标上，哪些格子是无人解决的市场缺口？（**方法四 · 白地分析**）
5. 在 4 个价格点上，分群购买意愿率分别是多少？（**Phase 1+2 logit 模拟**）
6. 上市该出哪几个 SKU？（**三轨决策矩阵**）

输出：**交付级 HTML 报告**（给产品/管理层）+ **方法详解 MD**（给分析师）。

## 何时不该用这个 skill

- 只有「该卖多少钱」的拍脑袋问题，没有任何竞品 / 用户数据 → 先让用户准备数据
- 已经有 BI 系统跑实时销售数据 → 那是 Phase 4 posterior 校准，不是本 skill 的工作
- 只想做财务利润核算（毛利率 / 成本回收期）→ 那是财务建模

## 输入合同（Inputs）

| 类别 | 必需 / 可选 | 格式 | 说明 |
|---|---|---|---|
| 竞品价格种子 | **必需** | CSV / 文本表格，最少 4-5 行 | 字段：brand, model, price, currency, market（其中 currency / market 必填，用于推断地区+扩展）|
| 本品规格 + 目标定价 | 可选 | 文本 / dict | 若给，模型会按这个 spec 跑预测；不给则只输出竞品锚定范围 |
| 竞品用户痛点 | **必需** | HTML（带 const DATA = {...}）/ CSV / parquet | 至少一份；HTML 用 `scripts/extract_html_data.py` 解码 |
| 竞品用户画像 | 推荐 | 同上 | 不给的话只能跑全市场加权，没法分群 P(buy) |
| Reddit / 公网讨论画像 + 痛点 | 可选 | 同上 | 给的话两源加权（默认 Reddit 0.4 / 竞品 0.6）|
| 品类配置 | 可选 | category-config JSON | 不给则按品类自动选默认配置；新品类要自定义 |
| 输出货币 | 可选 | EUR / USD / CNY / etc. | 不指定按种子 currency 推断 |

**最小可运行输入**：4 个竞品种子 + 1 份竞品痛点 HTML/CSV → 可出三法 ANCHOR + 缺口分析（缺 Phase 1+2 分群细节）。

## 流水线 · 6 步

按下面顺序跑。**不要跳步**，每一步的输出是下一步的输入。中间产物全部落盘到 `<工作目录>/pricing_outputs/`。

### Step 1 · 验证输入完整性

```python
# 检查 4 个必需输入是否齐全：
1. 竞品种子 CSV（≥ 4 行，含 brand/model/price/currency/market）
2. 竞品痛点数据（HTML 或 CSV）
3. 品类标识（或显式 category-config 路径）
4. 工作目录（落盘位置）

# 不齐全 → 提示用户补，**不要瞎猜**默认值。
```

→ 详见 `references/input-formats.md`

### Step 2 · 扩展竞品到 15 个（WebSearch）

用户给的 4-5 个是「种子」，需要扩到 12-15 个才能让 Hedonic 回归有自由度。

```bash
python scripts/expand_competitors.py \
  --seeds <种子 CSV> \
  --target-count 15 \
  --output <输出 spec_matrix.csv>
```

脚本会：
1. 从种子推断品类 + 市场（基于 brand/model 关键词 + WebSearch）
2. 用 WebSearch 搜「<品类> top sellers <市场>」补齐到 15 个
3. 对每个新加的竞品 WebSearch 该型号的：当前售价、WiFi 代/规格、端口、覆盖、品牌等
4. 输出统一格式的 `spec_matrix.csv`

→ 详见 `references/method-1-hedonic.md` 的输入规范

### Step 3 · 加载品类配置

```bash
# 优先级：用户指定 > 自动推断 > 失败时让用户选
config = load_category_config(
  user_specified_path or auto_detect_from_seeds()
)
```

**默认配置已为 3 个品类预建**（见 `references/default-configs/`）：
- `wifi-mesh-router.json` — MeshNode 项目用的那套（v1 复刻）
- `kvm-switch.json` — KVM 切换器
- `smart-kettle.json` — 智能水壶

**新品类**：让用户基于 `references/config-schema.md` 写一份，落到 `references/default-configs/<category>.json`。

配置内容（核心字段）：
- `price_bands` — 5 个价格分档（per node / per unit）
- `pain_themes` — 12-15 个痛点主题 + 关键词
- `signal_map` — 12-17 个购买信号定义
- `own_brand_solve_weights` — 本品对每个痛点的解决能力（0-1）
- `currency` + `category_label`

→ 详见 `references/config-schema.md`

### Step 4 · 跑 Phase 0 · 三法

```bash
python scripts/pipeline_phase0.py \
  --spec-matrix <spec_matrix.csv> \
  --pain-data <竞品痛点 JSON 解码后> \
  --reddit-pain <可选 Reddit 痛点 JSON> \
  --own-product-spec <可选本品 spec dict> \
  --config <category-config.json> \
  --output-dir pricing_outputs/
```

输出：
- `summary.json` — Hedonic + Pareto + Pain-weighted 三个价格 + 三法中位（ANCHOR）
- `pain_weighted.csv` — 痛点贡献明细

→ 方法细节：
  - `references/method-1-hedonic.md`
  - `references/method-2-pareto.md`
  - `references/method-3-pain.md`

### Step 5 · 跑 Phase 0.5 + Phase 1 + Phase 2

```bash
# 5a. 第四法 · 市场缺口
python scripts/pipeline_market_gap.py \
  --pain-data <竞品 + Reddit 痛点 JSON> \
  --spec-matrix <spec_matrix.csv> \
  --config <category-config.json> \
  --output-dir pricing_outputs/

# 5b. Phase 1 · 信号抽取（cluster-aggregated proxy）
python scripts/pipeline_phase1.py \
  --persona-data <竞品 + Reddit personas JSON> \
  --pain-data <竞品 + Reddit pains JSON> \
  --config <category-config.json> \
  --output-dir pricing_outputs/

# 5c. Phase 2 · 价格情景 logit
python scripts/pipeline_phase2.py \
  --phase0-summary pricing_outputs/summary.json \
  --phase1-signals pricing_outputs/segment_pricing_summary.csv \
  --config <category-config.json> \
  --output-dir pricing_outputs/
```

输出：
- `market_gap_matrix.csv` + `market_gap_top10.csv`
- `segment_pricing_summary.csv` — N 个分群 × 17 信号
- `price_scenario_conversion.csv` — N 分群 × 4 价格点 P(buy)
- `pricing_model_params.json` — β + ANCHOR

→ `references/method-4-gap.md` + `references/phase-1-2-logit.md`

### Step 6 · 生成 HTML 报告 + MD 方法详解

**交付级 HTML 报告**走 `data-team-skills:html-report` skill：

```python
# 调用 html-report skill，传入：
{
  "report_title": "<品类> 定价综合报告 v1",
  "sections": [
    {"label": "一页全景",       "content": <Section 1 概览 KPI + insight>},
    {"label": "分析一 · 竞品对位", "content": <三法 KPI + 子图 1/2/3>},
    {"label": "分析二 · 谁会买",    "content": <17 信号 + 分群表>},
    {"label": "分析三 · 价格情景",  "content": <价格曲线 + 分群对比>},
    {"label": "分析四 · 市场空缺",  "content": <Top 缺口图 + 价位竞品表>},
    {"label": "定价决策",          "content": <3 轨 SKU 矩阵>},
    {"label": "上市路线图",        "content": <结论 + 行动 + 术语表>},
  ],
  "charts": [
    {id: "chart-three-methods",  type: "h-bar",       data: ...},  # 三法对比
    {id: "chart-spec-impact",    type: "h-bar",       data: ...},  # Hedonic 系数
    {id: "chart-perf-price-map", type: "scatter",     data: ...},  # Pareto
    {id: "chart-top-pains",      type: "h-bar",       data: ...},  # Top 痛点
    {id: "chart-price-scenarios","type": "v-bar",     data: ...},  # 4 价格 P(buy)
    {id: "chart-segment-curves", type: "multi-line",  data: ...},  # 分群曲线
    {id: "chart-gap-ranking",    type: "h-bar",       data: ...},  # 缺口排序
  ],
  "currency": "<EUR / USD / ...>",
  "audience": "product_management_executive"   # 强制业务语言，避免英文术语
}
```

→ 详见 `references/html-report-handoff.md`

**方法详解 MD** 直接用 `scripts/render_method_doc.py` 渲染（模板内置）。

## 输出合同（Outputs）

| 文件 | 路径 | 用途 |
|---|---|---|
| HTML 业务报告 | `<工作目录>/<品类>_定价综合报告.html` | 给产品 / 管理层 |
| MD 方法详解 | `<工作目录>/<品类>_定价方法详解.md` | 给数据分析师 / 复用 |
| 中间产物 | `<工作目录>/pricing_outputs/*.csv,*.json` | Phase 4 真实销售校准时用 |
| 复用脚本 | `<工作目录>/lib/*.py` | 下次跑同品类可复用 |

## 关键约束 · 跨品类都成立

### 业务语言（不要专业术语）

HTML 报告**严禁出现**：Hedonic / Pareto / β / logit / sigmoid / P(buy) / Bayesian / ANCHOR / posterior / Cohen's κ / F1 / cluster-aggregated。
**用业务说法替换**：规格驱动定价 / 性价比前沿 / 权重系数 / 概率模型 / 购买意愿率 / 基准价 / 真实销售反推 / 一致性检查 / 准确率 / 分群聚合。

MD 方法详解可以用术语，因为读者是分析师。

### 跳过 Phase 1.5 人工标注（推荐 LLM 自动校准代替）

v1 baseline 不走 N=200 人工标注（人手贵）。校准走两条：
- **主**：Phase 4 上市后真实销售 posterior（需 launch 前埋点）
- **辅**：**LLM 自动代理标注**（推荐 launch 前做）— 用 DeepSeek API 跑全量标注，25-30 分钟完成，成本 < $2，比人工 N=200 快 200 倍且更可靠

调用方式：
```bash
# 准备：把评论 corpus 转成 sample_full.csv (含 row_id/text/segment_k20/source)
export DEEPSEEK_API_KEY=sk-xxx
python scripts/llm_annotate_deepseek.py --input sample_full.csv --output llm_scores.parquet --concurrency 15
python scripts/compute_calibration.py --llm-scores llm_scores.parquet --sample-meta sample_full.csv --prior-segments segment_pricing_summary.csv --config <category>.json --output-dir calibrated/
python scripts/rerun_phase2_calibrated.py --phase0-summary summary.json --phase1-signals segment_pricing_summary.csv --config-v1 <category>.json --config-v2 calibrated/pricing_model_params_v2_calibrated.json --output-dir calibrated/
```

校准输出：
- `calibration_summary.csv` — 每个信号的 Pearson r + 等级 (trustworthy / grey / discard / rare_no_prior) + β old/new
- `pricing_model_params_v2_calibrated.json` — 修正后的完整 config
- `before_after_comparison.csv` — P(buy) 前后对比（典型校准后下调 5-10pp）

样例参考：`examples/meshnode-v2-calibrated/`

### 货币统一

整份 HTML 报告**统一一种货币**（不要混 EUR/USD）。若用户输入种子有 USD 也有 EUR，统一换算到目标货币后展示，注明汇率。

### 心理价格红线（按品类）

每个 category-config 必须定义至少 3 条「禁止价位」红线：
- 单件 hard cap（用户脑里的「单件不超过 X」）
- 组合套餐 anchor（用户对全套预算的天花板）
- anger zone（超出会触发愤怒退货的总价）

→ Phase 0.5 报告里 `禁止组合 warning` 框直接用这 3 条红线。

## 失败模式 · 这些情况会出错

| 症状 | 原因 | 修复 |
|---|---|---|
| Hedonic R² < 0.5 | spec_matrix 异质性太高，或样本 < 8 | 加 WebSearch 拉更多同品类竞品；或剔除非可比品 |
| Phase 2 P(buy) 全部 > 95% 或 < 5% | 信号尺度没校准 | 检查 SIGNAL_MAP 的 cluster-rate 累积上限是否 cap 在 0.6 |
| 缺口分析 D / E band 永远 0 score | 品牌归因稀疏，未命中关键词 | 扩 BRAND_KEYWORDS 关键词；或接受「只看 A-C 段缺口」 |
| HTML 报告里冒出英文 β / Hedonic 字样 | render 没走业务语言 mode | 确认调 html-report skill 时 audience=`product_management_executive` |
| 中间数据脏 → 后续步报错 | category-config 字段名拼写错 | 用 `references/config-schema.md` 的 JSON Schema 验证 |

## 复用 checklist · 应用到新品类

每个新品类（如「智能门锁」「无人机」）的接入工作约 2-3 工作日：

1. **配置文件** `<category>.json`（参考 default-configs/，重写痛点主题 + 信号 + 品牌价格映射）
2. **品类适配的 own-brand-solve 权重**（GL.iNet 在该品类的真实可解能力）
3. **WebSearch 关键词**（如「smart kettle deutsch test」「KVM switch best HDMI」）
4. **第一次跑通后人工 review** 三法中位是否合理（不合理则调 `PAIN_KEYWORD_MAP` 权重）

完整跑一次（已有配置）：5-15 分钟。

## 相关 skills

- `data-team-skills:html-report` — 本 skill 必调用（生成 HTML 报告）
- `customer-persona-clustering` — 如果用户只给评论 CSV 还没分群，先用这个 skill 跑出 personas + pains
- `social-reviews-analyzer` — Reddit / 论坛评论抽取（生成 Reddit pain 输入）

## 文件清单

```
~/.claude/skills/pricing-pipeline/
├── SKILL.md                           # 本文件（主工作流 + 输入合同）
├── references/
│   ├── input-formats.md               # 4 种输入文件的字段定义
│   ├── config-schema.md               # category-config JSON Schema
│   ├── method-1-hedonic.md            # 方法一详解
│   ├── method-2-pareto.md             # 方法二详解
│   ├── method-3-pain.md               # 方法三详解
│   ├── method-4-gap.md                # 方法四白地分析详解
│   ├── phase-1-2-logit.md             # Phase 1 信号 + Phase 2 logit 详解
│   ├── html-report-handoff.md         # 调用 html-report skill 的参数模板
│   └── default-configs/
│       ├── wifi-mesh-router.json      # MeshNode 项目复刻
│       ├── kvm-switch.json
│       └── smart-kettle.json
├── scripts/
│   ├── extract_html_data.py           # HTML → const DATA JSON
│   ├── decode_pain_pages.py           # gzip+b64 page 解码
│   ├── expand_competitors.py          # 4-5 种子 → 15 个 (WebSearch)
│   ├── pipeline_phase0.py             # 三法 (Hedonic + Pareto + Pain)
│   ├── pipeline_phase1.py             # 信号抽取
│   ├── pipeline_phase2.py             # 价格情景 logit
│   ├── pipeline_market_gap.py         # Phase 0.5 第四法
│   └── render_method_doc.py           # MD 方法详解生成
├── assets/
│   └── competitor_seed_template.csv   # 用户填 4-5 行的模板
└── evals/
    └── evals.json                     # 3 端到端测试用例
```

---

*GL.iNet Data Team · v1 baseline · 由 MeshNode 定价项目沉淀；可复用到任何消费电子品类*
