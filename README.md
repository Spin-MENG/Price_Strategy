# Price Strategy · 数据驱动定价分析流水线

> Claude Code skill · 沉淀自 GL.iNet MeshNode 定价项目，可复用到任何消费电子品类

## 这个 skill 解决什么问题

给一个**新产品（或已定 PPT 价的产品）做端到端定价决策**，回答：

1. 按 spec 拟合，该产品该卖多少？ **方法一 · 竞品规格回归（Hedonic）**
2. 在「性能 × 价格」前沿上，落在哪里合理？ **方法二 · 性价比前沿（Pareto）**
3. 用户痛点能让我加价 / 减价多少？ **方法三 · 痛点加权**
4. 在「价位段 × 痛点」二维坐标上，哪些是无人解决的市场缺口？ **方法四 · 白地分析（Blue Ocean）**
5. 在 4 个价格点上，分群购买意愿率分别是多少？ **Phase 1+2 · 概率模型**
6. 上市该出哪几个 SKU？ **三轨决策矩阵**

**输出**：交付级 HTML 业务报告（给产品/管理层）+ 方法详解 MD（给分析师）。

## 安装

```bash
cd ~/.claude/skills/
git clone https://github.com/Spin-MENG/Price_Strategy.git pricing-pipeline
# 重启 Claude Code 即可在 skills 列表里看到 pricing-pipeline
```

## 最少输入

| 输入 | 必需 | 格式 | 说明 |
|---|---|---|---|
| 4-5 个竞品种子 | ✓ | CSV（brand/model/price/currency/market） | 自动 WebSearch 扩展到 15 个 |
| 竞品用户痛点 | ✓ | HTML / CSV | customer-persona-clustering 输出可直接喂 |
| 本品规格 + 定价 | 可选 | dict | 不给用配置默认值 |
| Reddit 痛点 / 画像 | 可选 | HTML / CSV | 给则两源加权 |

## 用法

```
> 用 pricing-pipeline 给智能水壶做定价分析。
> 竞品种子：Smarter iKettle €169 / Bosch Styline €115 / Tefal €55 / Xiaomi €70 / Philips €105
> 本品 1.7L 2200W 温控保温 App，PPT €80
> 用户痛点 HTML: ./kettle_pain.html
> 货币 EUR；输出落到 ./kettle_pricing/
```

Claude 会自动按 6 步流程跑完，产出 HTML 报告 + MD 方法详解。

## 已支持品类（预建配置）

| 品类 | 配置 |
|---|---|
| WiFi Mesh 路由器 | `references/default-configs/wifi-mesh-router.json` |
| KVM 切换器 | `references/default-configs/kvm-switch.json` |
| 智能水壶 | `references/default-configs/smart-kettle.json` |

**新品类**：基于 `references/config-schema.md` 写一份 JSON 配置即可。2-3 工作日上线。

## 文件结构

```
pricing-pipeline/
├── SKILL.md                              # Claude Code 主工作流（必读）
├── README.md                             # 本文件
├── references/
│   ├── input-formats.md                  # 输入文件规范
│   ├── config-schema.md                  # category-config JSON schema
│   ├── method-1-hedonic.md               # 方法一详解（含失效模式）
│   ├── method-2-pareto.md                # 方法二详解
│   ├── method-3-pain.md                  # 方法三详解
│   ├── method-4-gap.md                   # 方法四白地分析
│   ├── phase-1-2-logit.md                # Phase 1 信号 + Phase 2 logit
│   ├── html-report-handoff.md            # 调 data-team-skills:html-report 的参数模板
│   └── default-configs/
│       ├── wifi-mesh-router.json
│       ├── kvm-switch.json
│       └── smart-kettle.json
├── scripts/
│   ├── extract_html_data.py              # HTML → const DATA JSON
│   ├── decode_pain_pages.py              # gzip+b64 K-level page 解码
│   ├── expand_competitors.py             # 4-5 种子 → 15 (WebSearch)
│   ├── convert_legacy_features_csv.py    # 旧版 features.csv → spec_matrix.csv
│   ├── pipeline_phase0.py                # 三法（Hedonic + Pareto + Pain）
│   ├── pipeline_phase1.py                # 信号抽取
│   ├── pipeline_phase2.py                # 价格情景 logit
│   ├── pipeline_market_gap.py            # 第四法白地
│   └── render_method_doc.py              # MD 方法详解生成
├── assets/
│   └── competitor_seed_template.csv      # 用户填 4-5 行的模板
└── evals/
    └── evals.json                        # 3 个端到端测试用例
```

## 设计原则

1. **配置驱动**：每个新品类只换 `references/default-configs/<category>.json`，pipeline 通用
2. **业务语言**：HTML 报告严禁出现 Hedonic / β / logit / P(buy) 等术语；MD 给分析师可保留
3. **跳过 Phase 1.5 人工标注**：上市后用真实销售 posterior 校准更经济
4. **货币统一**：报告整份一种货币（不要混 EUR/USD）
5. **心理价格红线**：每个配置必须定义 3 条 hard cap，写进「禁止组合」warning

## 校准策略

v1 baseline **不做** N=200 人工标注（人手贵）。校准走两条：
- **主**：Phase 4 上市后真实销售 posterior（需 launch 前埋点 segment 标签）
- **辅**：LLM 自动代理标注（可选 · ~$25 · 3 小时跑完）

## 关联 skills

- `data-team-skills:html-report` — 必调用，生成 HTML 报告
- `customer-persona-clustering` — 如果只有 raw 评论 CSV，先用这个产出 personas + pains
- `social-reviews-analyzer` — Reddit / 论坛评论抽取

## License

Internal use by GL.iNet Data Team.

## Credits

源自 GL.iNet 内部 MeshNode 定价项目（2026 Q2）。
