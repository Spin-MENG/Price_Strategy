# 输入文件格式规范

## 1. 竞品种子 CSV（**必需**）

### 字段（必填）
```csv
brand,model,price_per_unit,currency,market
TP-Link,Deco BE25,73,EUR,DE
Amazon eero,eero 7,80,EUR,DE
TP-Link,Deco X50,58,EUR,DE
Google,Nest Wifi Pro,153,EUR,DE
NETGEAR,Orbi 370,217,EUR,DE
```

### 字段说明
| 字段 | 必填 | 说明 |
|---|---|---|
| `brand` | ✓ | 品牌名（用于品牌价格归因 + WebSearch）|
| `model` | ✓ | 型号（如 "Deco BE25"）|
| `price_per_unit` | ✓ | 单件价（数字）|
| `currency` | ✓ | EUR / USD / CNY / GBP / etc. |
| `market` | ✓ | DE / FR / US / UK / CN / etc.（ISO 2 字母）|
| `pack_size` | 推荐 | 包装数；不填默认 1 |
| 其他 spec 列 | 可选 | 有则填，没有 WebSearch 时补 |

### 数量要求
- **最少 4 行**（不够会导致 Hedonic 回归无意义）
- 推荐 5 行（让 WebSearch 扩展更可控）
- 上限 15 行（更多就不必扩展了）

### 货币/市场混合
**不要**在同一份种子里混合多种 currency / market。如果有多个市场，分开跑 pipeline。

---

## 2. 本品规格 + PPT 价格（可选）

### 格式（JSON）
```json
{
  "wifi_gen": 7.0,
  "phy_total_mbps": 3570,
  "max_port_gbe": 2.5,
  "coverage_sqm": 604,
  "has_6ghz": 0,
  "is_premium_brand": 0,
  "ppt_price_eur_per_unit": 73
}
```

字段名必须与 `config.spec_features[].col` 对得上。

### 不给本品 spec 时
模型会用 `config.own_product_default_spec`，意味着 Phase 0 Hedonic 预测的是「PPT 默认 spec 的价格」。多数情况这是 OK 的。

---

## 3. 竞品用户痛点（**必需**）

### 来源：customer-persona-clustering / social-reviews-analyzer 输出的 HTML

这两个 skill 输出的 HTML 都含 `const DATA = {...};` 嵌入 JSON。

### 处理步骤
```bash
# Step 1: 提取 HTML 里的 DATA
python scripts/extract_html_data.py 竞品评论痛点.html --output 竞品痛点.json

# Step 2: 解码内嵌的 gzip+base64 K-level 页
python scripts/decode_pain_pages.py 竞品痛点.json --output 竞品痛点_decoded.json
```

### 结构示例（decoded 后）
```json
{
  "product_name": "...",
  "variants": {
    "v0": {
      "label": "min_cluster_size=5",
      "defaultK": 5,
      "k_to_payload": {
        "5": {
          "personas": [...],
          "persona_sizes": {...},
          "clusters": [...],
          "rate_matrix": [[...]],
          "quadrant": [{"type":"pain","name":"...","relevance_pct":...,"satisfaction":...,"samples":[...]}, ...]
        },
        "10": {...}
      }
    }
  }
}
```

### 替代格式：CSV
如果用户给的是 raw CSV（每行 = 一条评论 + 痛点 label），需要先跑 `customer-persona-clustering` skill 把它转成上面的结构。

---

## 4. Reddit / 公网讨论画像 + 痛点（可选）

### 处理同上
```bash
python scripts/extract_html_data.py Reddit痛点.html --output Reddit痛点.json
python scripts/decode_pain_pages.py Reddit痛点.json --output Reddit痛点_decoded.json
```

### 加权规则（自动）
- 给了 Reddit → 三法痛点加权用 0.4 (Reddit) / 0.6 (Competitor)
- 没给 Reddit → Competitor 用 1.0 全权重

### 何时该给 Reddit
- 用户讨论广（如 mesh router, smart kettle 这种品类）→ 给，能拉出广场视角
- 用户少（如某些工业品）→ 没必要给
- 给 Reddit 后 Phase 0.5 第四法的覆盖更广（多源痛点，多 cluster 命中品牌）

---

## 5. 品类配置（可选 — 推荐用预设）

`references/default-configs/<category>.json` 包含 3 个预设：
- wifi-mesh-router
- kvm-switch
- smart-kettle

### 用预设
```bash
--config references/default-configs/wifi-mesh-router.json
```

### 新品类自定义
1. 复制最相近的预设
2. 按 `config-schema.md` 重写 11 组字段
3. 重点改：`pain_themes` / `pain_to_solve_weight` / `meshnode_solve` / `signals` / `brand_price_per_unit` / `brand_keywords`

---

## 6. 输出货币 + 工作目录

```bash
--output-dir <工作目录>     # 中间产物 + HTML 报告落盘位置
```

货币：从 config / 种子 CSV 推断；不冲突就用 config 的。
