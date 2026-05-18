# 方法 2 · 性价比前沿对位（Pareto Frontier）

## 目的

在「性能综合分 × 价格」坐标系上找最有效率的产品组合，看本品落在哪。

## 算法

1. 性能综合分 = mean(z-score) over 所有 in_hedonic spec features
2. Pareto 前沿 = 沿 price 升序遍历，每次 perf 上升就纳入前沿
3. 在前沿上对本品的 perf 做线性插值，得对位价

```python
def pareto_frontier(df_sorted_by_price):
    is_pareto = []
    best_perf = -inf
    for row in df_sorted_by_price:
        if row.perf_score > best_perf:
            is_pareto.append(True)
            best_perf = row.perf_score
        else:
            is_pareto.append(False)
    return is_pareto
```

## 输入 / 输出

输入：spec_matrix（同方法 1）+ 本品 spec dict
输出：
- own_perf_score（本品在 spec 维度的相对位置）
- frontier_implied_price（对位价，3-pack 等效）
- pareto_points（前沿点列表）
- all_points + is_pareto flag

## 报告呈现

HTML 报告 Section 2「方法二详情 · 性价比座标图」散点图：
- 横轴：配置综合分（业务说法）
- 纵轴：3-pack 价格
- 绿色虚线 = Pareto 前沿
- 灰色 = 被支配点（贵但 spec 一般 — 用户失望转投的池）
- 橙色菱形 = 本品落点

## 业务读法

```
- 本品落在前沿上 → 性价比合理
- 本品落在前沿上方 → 高于市场前沿，需要差异化故事补回
- 本品落在前沿下方 → 性价比超群，但可能利润不够
```

## 局限

- "性能"的定义可争议（不同 PM 给不同权重 → perf_score 不一样）
- 不能捕捉 brand goodwill / 生态系统价值
- 小样本（n < 10）的前沿很容易被异常值带歪
