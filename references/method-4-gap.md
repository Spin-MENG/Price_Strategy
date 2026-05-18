# 方法 4 · 痛点-价格白地分析（Blue Ocean Gap）

## 目的

前三法回答「该卖多少」；第四法回答 **「在多少钱 × 哪种痛点的二维坐标上，有大量未解的痛 + 没有强势竞品 = 该卡的市场缺口」**。

## 算法（6 步）

1. **品牌归因**：扫描每个 pain cluster 的 name + samples，找品牌关键词 → 算 brand_share
2. **主题归类**：按 `config.pain_themes` 的关键词，把 cluster 映射到 1 个主题
3. **band 映射**：每个品牌按 `config.brand_price_per_unit_eur` 映射到价格分档
4. **pain_density**：
   ```
   pain_density(band, theme) = Σ rel_pct × max(|sat|, 0.5) × brand_share_in_band
   ```
5. **under_served_factor**：
   ```
   under_served_factor(band) = 1 - best_positive_satisfaction_in_band / 2
   ```
6. **gap_score**：
   ```
   gap_score = pain_density × meshnode_solve × under_served_factor
   ```

## 输入

- 竞品 + Reddit 痛点 decoded JSON（任一即可）
- 品类配置（含 `brand_price_per_unit_eur`, `brand_keywords`, `pain_themes`, `meshnode_solve`）

## 输出

| 文件 | 内容 |
|---|---|
| `market_gap_matrix.csv` | 全 band × theme 痛点密度（5×10 ≈ 50 行）|
| `market_gap_top10.csv` | Top 15 gap_score + SKU 推荐 |

## 报告呈现

HTML 报告 Section 5「分析四 · 市场空缺扫描」：
- Top 8 缺口横向柱（按 gap_score 排序）
- 各 band × 竞品 × MeshNode 落点表
- 2-3 个 insight 框讲最大缺口的故事

## 业务读法

```
gap_score ≥ 1.0  →  强机会，应卡
gap_score 0.5-1.0 →  二级机会
gap_score < 0.5  →  弱机会或防守
```

## 局限

1. **品牌归因稀疏**：cluster 名通常不带品牌（如 "网络稳定性"），导致很多 cluster 被「均分到 5 band 作 baseline」 — A/B/D/E 的相对排序不确定性大
2. **best_pos_sat max-aggregation**：同 band 一个产品做得好就拉高 under_served，可能低估真实缺口
3. **meshnode_solve 手工编码**：基于既有产品认知 launch 后会调
4. **没量化 TAM**：gap_score 高不等于赚得多，要乘市场规模（Phase 4 校准时做）

## 改进方向

- 用 brand-specific positive sat（不是 band max）
- 加入 TAM × ARPU 估算把缺口换成「机会金额」
- 用 LLM 给每个 cluster 做品牌归因（绕过 keyword 缺失问题）
