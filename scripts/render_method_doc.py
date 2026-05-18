"""
方法详解 MD 生成（给分析师看）。

根据 pricing_outputs/ 里的结果 + category-config，生成一份独立 MD。

用法：
  python render_method_doc.py \
    --output-dir <pricing_outputs/> \
    --config <category-config.json> \
    --out <category>_定价方法详解.md
"""

import argparse
import json
from pathlib import Path

import pandas as pd


TEMPLATE = """# {category_label} 定价方法详解 v1

> **配套报告**：`{html_report_name}`
> **撰写**：GL.iNet Data Team · {date}
> **目标读者**：定价决策方、PM、分析师
> **可独立交付**：是

---

## 0 · 方法全景

```
                        ┌──── 方法 1 · 竞品规格回归 ────┐
Phase 0 · 竞品锚定 ────┼──── 方法 2 · 性价比前沿对位 ──┼──→ 基准价
（三法）               └──── 方法 3 · 用户痛点加权 ────┘   ({mid:.0f} {currency} / 3-pack)
                                                              │
Phase 0.5 · 第四法                                            │
痛点 × 价格白地分析 ───────────────────→ 缺口机会清单         │
                                                              │
Phase 1 · 信号抽取 ────→ {n_signals} 条 0/1/2 信号 × {n_segments} 个分群
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
- R² = {hedonic_r2:.3f} / 调整 R² = {hedonic_adj:.3f}
- 样本 n = {hedonic_n}
- 本品预测：{hedonic_pred:.0f} {currency}（95% PI [{hedonic_lo:.0f}, {hedonic_hi:.0f}]）

### 1.2 方法 2：性价比前沿对位（Pareto）

**目的**：在「性能 × 价格」坐标系上找最有效率的产品，看本品该落在哪。

**v1 结果**：
- 本品性能综合分 = {own_perf:+.3f}
- 前沿对位价 = **{frontier_price:.0f} {currency}**

### 1.3 方法 3：痛点加权（Pain-weighted）

**公式**：
```
total_adjustment_pct = Σ_cluster  rel_pct × max(|sat|, 0.5) × weight
```

**v1 结果**：
- 净调整：{pain_adj:+.2f}%
- 痛点调整后价：{pain_price:.0f} {currency}

### 1.4 三法综合

- min {p_min:.0f}  /  mid **{p_mid:.0f}**  /  max {p_max:.0f}  → ANCHOR = {p_mid:.0f} {currency}

---

## 2 · Phase 0.5 · 第四法（市场缺口分析）

`gap_score = pain_density × meshnode_solve × under_served_factor`

→ 完整 top 15 缺口见 `pricing_outputs/market_gap_top10.csv`

---

## 3 · Phase 1 · 信号抽取（{n_signals} 条）

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
- base_logit = {base_logit}
- 价格弹性 = {elasticity}
- {n_signals} 个信号 β 权重见 `pricing_outputs/pricing_model_params.json`

---

## 6 · 心理价格红线

| 红线 | 来源 | 值 |
|---|---|---|
| 单件 hard cap | 用户心理上限 | **{hard_cap}** {currency} |
| 套餐预算 anchor | 多件总价心理预算 | **{multi_anchor}** {currency} |
| 总价 anger zone | 触发愤怒退货的总价 | **{anger_zone}** {currency} |

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

*GL.iNet Data Team · {date} · v1 baseline · 可独立交付*
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--html-report-name", default=None,
                   help="配套 HTML 报告文件名（仅作交叉引用展示）")
    p.add_argument("--date", default="2026-05-18")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    config = json.loads(Path(args.config).read_text())
    summary = json.loads((out_dir / "summary.json").read_text())
    seg = pd.read_csv(out_dir / "segment_pricing_summary.csv")

    h = summary["hedonic"]
    f = summary["frontier"]
    pa = summary["pain"]
    cr = summary["combined_range"]

    html_report_name = args.html_report_name or f"{config['category_id']}_定价综合报告.html"
    rendered = TEMPLATE.format(
        category_id=config["category_id"],
        category_label=config["category_label"],
        html_report_name=html_report_name,
        date=args.date,
        currency=config["currency"],
        mid=cr["mid"],
        hedonic_r2=h["r2"], hedonic_adj=h["adj_r2"], hedonic_n=h["n"],
        hedonic_pred=h["own_pred"], hedonic_lo=h["own_pi_low"], hedonic_hi=h["own_pi_high"],
        own_perf=f["own_perf_score"], frontier_price=f["frontier_implied_price"],
        pain_adj=pa["weighted_net_adjustment_pct"], pain_price=pa["pain_adjusted_price"],
        p_min=cr["min"], p_mid=cr["mid"], p_max=cr["max"],
        n_signals=len(config["signals"]), n_segments=len(seg),
        base_logit=config["base_logit"], elasticity=config["price_elasticity"],
        hard_cap=config["psychological_red_lines"]["single_unit_hard_cap"],
        multi_anchor=config["psychological_red_lines"]["multi_unit_budget_anchor"],
        anger_zone=config["psychological_red_lines"]["total_anger_zone"],
    )
    Path(args.out).write_text(rendered)
    print(f"→ {args.out}  ({len(rendered)} chars)")


if __name__ == "__main__":
    main()
