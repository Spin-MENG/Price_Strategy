"""
竞品种子扩展（WebSearch 驱动）。

入：4-5 个竞品种子 CSV（brand, model, price, currency, market 必填）
出：完整 spec_matrix.csv，扩到 target_count（默认 15）个竞品

本脚本不直接调 WebSearch（那是 LLM tool）。它输出一份「待 WebSearch 的清单」
+ 解析框架，由调用方（Claude）执行 WebSearch 并把结果回填进同一个 CSV。

使用方式：
  python expand_competitors.py \
    --seeds <seed.csv> \
    --target-count 15 \
    --output <spec_matrix.csv>

输出两份文件：
  - <spec_matrix.csv>  含种子 + 占位行（spec 为空待填）
  - <spec_matrix>.search_plan.md  WebSearch 计划（给 Claude 看）
"""

import argparse
import csv
from pathlib import Path


REQUIRED_SEED_COLS = ["brand", "model", "price_per_unit", "currency", "market"]

# 用户在 spec_matrix 里期望的完整列（按品类配置有差异，这里给通用骨架）
SPEC_COLS_GENERIC = [
    "brand", "model", "price_per_unit", "currency", "market", "pack_size",
    # 下面这些字段按品类不同，让用户/Claude 在 WebSearch 后填
    "wifi_gen", "phy_total_mbps", "max_port_gbe", "coverage_sqm",
    "has_6ghz", "is_premium_brand", "n_ports", "n_bands", "ram_mb_num",
    "release_year", "notes",
]


def load_seeds(path: Path) -> list[dict]:
    with open(path) as f:
        rdr = csv.DictReader(f)
        seeds = list(rdr)
    missing = [c for c in REQUIRED_SEED_COLS if c not in (seeds[0].keys() if seeds else [])]
    if missing:
        raise SystemExit(f"种子 CSV 缺必需字段：{missing}")
    return seeds


def write_skeleton(seeds: list[dict], spec_cols: list[str],
                   target_count: int, output: Path) -> int:
    """种子 + (target_count - len(seeds)) 个占位行写入 CSV。返回需 WebSearch 的占位行数。"""
    rows = []
    for s in seeds:
        row = {c: s.get(c, "") for c in spec_cols}
        if "pack_size" not in row or not row["pack_size"]:
            row["pack_size"] = 1
        rows.append(row)

    need = max(0, target_count - len(seeds))
    for i in range(need):
        rows.append({c: f"<TODO_{i+1}>" for c in spec_cols})

    with open(output, "w") as f:
        wr = csv.DictWriter(f, fieldnames=spec_cols)
        wr.writeheader()
        for row in rows:
            wr.writerow(row)
    return need


def write_search_plan(seeds: list[dict], need: int, output: Path) -> None:
    markets = sorted({s["market"] for s in seeds})
    currencies = sorted({s["currency"] for s in seeds})
    brands = sorted({s["brand"] for s in seeds})

    plan = f"""# Competitor Expansion · WebSearch Plan

## Inputs

- {len(seeds)} 个种子已就位
- 需要再 WebSearch **{need}** 个同品类竞品填补 `<TODO_N>` 行

## 上下文（从种子推断）

- **品类**：{", ".join(brands)} 的同品类（请 LLM 据 brand+model 推断）
- **市场**：{", ".join(markets)}
- **货币**：{", ".join(currencies)}

## WebSearch 步骤

### Step 1 · 推断品类
查看种子中所有 brand+model 字段，归纳成 1 句品类描述。例：
- `TP-Link Deco BE25` + `eero 7` + `Nest Wifi Pro` → "consumer WiFi 7 mesh router"
- `Tesmart HDMI 2.0 4K` + `Level1Techs Optix` → "4K HDMI KVM switch for dual workstation"

### Step 2 · WebSearch 拉竞品清单
以「品类描述 + best/top + 市场」为查询。例：
- `"best WiFi 7 mesh router 2026 Germany Amazon"`
- `"top 4K KVM switch dual monitor 2025 reviews"`

从结果中挑出 **{need}** 个未在种子中的型号（按销量/曝光度 / 评论数排序）。

### Step 3 · 对每个新竞品 WebSearch 详细 spec + 当前售价
查询模板：
- `"<brand> <model> price <market_currency>"`
- `"<brand> <model> specifications WiFi GbE coverage"`
- `"<brand> <model> review release year"`

字段填写规则：

| 字段 | 怎么填 |
|---|---|
| `price_per_unit` | 主流零售价中位数（取 3 个来源平均）|
| `currency` | 与种子保持一致 |
| `market` | 与种子保持一致 |
| `pack_size` | 通常 1（single）；如果该型号默认套装则填套装数 |
| `wifi_gen` / `phy_total_mbps` / 等 | 按官方 spec 表填；找不到留空 |
| `release_year` | 第一次上市年份；不确定填 2024 |
| `notes` | WebSearch 来源摘要 / 不确定项标注 |

### Step 4 · 回填 CSV
逐行替换 `<TODO_N>` 占位为 WebSearch 得到的值。完成后整份 CSV 应有 ≥ 12 行可用数据（spec 缺失 ≤ 20%）。

### Step 5 · 校验
- 价格区间合理（最贵 ≤ 最便宜的 6×；离群值检查）
- 主要 spec 列缺失率 ≤ 30%
- 至少有 1-2 个明显「被支配点」(贵但 spec 一般)，便于 Pareto frontier 可视化

完成后，把 `<spec_matrix.csv>` 喂给 `pipeline_phase0.py`。
"""
    output.write_text(plan)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", required=True, help="seed CSV path")
    p.add_argument("--target-count", type=int, default=15)
    p.add_argument("--output", required=True, help="spec_matrix.csv output")
    p.add_argument("--spec-cols", help="comma-sep custom column list (default: generic)")
    args = p.parse_args()

    seeds = load_seeds(Path(args.seeds))
    spec_cols = args.spec_cols.split(",") if args.spec_cols else SPEC_COLS_GENERIC

    need = write_skeleton(seeds, spec_cols, args.target_count, Path(args.output))
    plan_path = Path(args.output).with_suffix(".search_plan.md")
    write_search_plan(seeds, need, plan_path)

    print(f"→ {args.output}     ({len(seeds)} 种子 + {need} 待填占位 = {len(seeds)+need} 行)")
    print(f"→ {plan_path}       WebSearch 计划")
    print(f"\n下一步：让 Claude 按 search_plan.md 跑 WebSearch，回填 <TODO_N> 行。")


if __name__ == "__main__":
    main()
