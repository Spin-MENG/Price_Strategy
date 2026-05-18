# Category Config Schema

每个品类的定价 pipeline 都需要一份 `<category>.json` 配置。配置驱动所有 4 个方法的关键词、权重、价格分档。

## JSON Schema（必需字段）

```json
{
  "category_id":    "<kebab-case-id>",
  "category_label": "<中文显示名>",
  "category_label_en": "<English display name>",

  "currency": "EUR",
  "exchange_to_usd": 1.08,

  "default_market":  ["DE","FR","ES","IT","UK"],

  "psychological_red_lines": {
    "single_unit_hard_cap":       100,
    "multi_unit_budget_anchor":   400,
    "total_anger_zone":           500
  },

  "price_points_for_simulation":  [65, 73, 80, 90],
  "price_point_labels":           ["攻击价", "主力价", "标准价", "上限价"],

  "price_bands": [
    {"id":"A", "label":"sub-€90 (入门)",    "min": 0,   "max": 90},
    {"id":"B", "label":"€90-150 (中低)",    "min": 90,  "max": 150},
    {"id":"C", "label":"€150-220 (中价)",   "min": 150, "max": 220},
    {"id":"D", "label":"€220-330 (高端)",   "min": 220, "max": 330},
    {"id":"E", "label":"€330+ (顶级)",      "min": 330, "max": 9999}
  ],

  "brand_price_per_unit_eur": {
    "tp-link":   65,
    "deco":      65,
    "eero":      80,
    "amazon":    80,
    "netgear":   217,
    "orbi":      217,
    "asus":      225,
    "google":    153,
    "nest":      153,
    "avm":       179,
    "fritz":     179,
    "linksys":   333,
    "velop":     333,
    "devolo":    105,
    "tenda":     55,
    "huawei":    120,
    "xiaomi":    70,
    "ubiquiti":  250,
    "unifi":     250
  },

  "brand_keywords": {
    "tp-link":   ["TP-Link","tp-link","TPlink"],
    "deco":      ["Deco","DECO","deco"],
    "eero":      ["eero","Eero","EERO"]
  },

  "spec_features": [
    {"col": "wifi_gen",        "type": "ordinal", "in_hedonic": true},
    {"col": "phy_total_mbps",  "type": "numeric", "in_hedonic": true, "log": true},
    {"col": "max_port_gbe",    "type": "numeric", "in_hedonic": true},
    {"col": "coverage_sqm",    "type": "numeric", "in_hedonic": true, "log": true},
    {"col": "has_6ghz",        "type": "binary",  "in_hedonic": true},
    {"col": "is_premium_brand","type": "binary",  "in_hedonic": true}
  ],

  "own_product_default_spec": {
    "wifi_gen": 7.0,
    "phy_total_mbps": 3570,
    "max_port_gbe": 2.5,
    "coverage_sqm": 604,
    "has_6ghz": 0,
    "is_premium_brand": 0
  },

  "pain_themes": {
    "stability_handoff":     {"keywords": ["稳定性","断连","掉线","reboot","Mesh全链路","回程"]},
    "coverage_dead_zone":    {"keywords": ["覆盖","穿透","盲区","信号","WiFi全屋"]},
    "subscription_paywall":  {"keywords": ["订阅","subscription","Abo","paywall","付费"]},
    "firmware_lifecycle":    {"keywords": ["固件","firmware","更新","EOL","停止安全"]},
    "setup_app_complex":     {"keywords": ["初始配置","设置门槛","安装","App"]},
    "value_disappointment":  {"keywords": ["价格","性价比","心理预期","硬件规格与价值"]},
    "throughput_wired_bottleneck": {"keywords": ["千兆","CPU 限速","Bufferbloat"]},
    "pro_control_missing":   {"keywords": ["Pro options","高级设置","VLAN","QoS"]},
    "vendor_lockin_extension": {"keywords": ["同牌加购","兼容受阻","另买节点"]},
    "vpn_cgnat_block":       {"keywords": ["VPN","WireGuard","Tailscale","CGNAT"]},
    "own_brand_specific":    {"keywords": ["GL.iNet","Mudi","Flint"]}
  },

  "pain_to_solve_weight": {
    "stability_handoff":         0.06,
    "coverage_dead_zone":        0.05,
    "subscription_paywall":      0.09,
    "firmware_lifecycle":        0.06,
    "setup_app_complex":         0.03,
    "value_disappointment":      -0.06,
    "throughput_wired_bottleneck": 0.06,
    "pro_control_missing":       0.05,
    "vendor_lockin_extension":   0.04,
    "vpn_cgnat_block":           0.05,
    "own_brand_specific":        -0.10
  },

  "meshnode_solve": {
    "stability_handoff":         0.70,
    "coverage_dead_zone":        0.60,
    "subscription_paywall":      1.00,
    "firmware_lifecycle":        0.90,
    "setup_app_complex":         0.40,
    "value_disappointment":      0.80,
    "throughput_wired_bottleneck": 0.50,
    "pro_control_missing":       1.00,
    "vendor_lockin_extension":   0.80,
    "vpn_cgnat_block":           1.00,
    "own_brand_specific":        -0.50
  },

  "signals": {
    "coverage_pain_score":        {"beta": 1.20, "themes": ["coverage_dead_zone"]},
    "stability_pain_score":       {"beta": 1.40, "themes": ["stability_handoff"]},
    "subscription_aversion_score":{"beta": 1.60, "themes": ["subscription_paywall"]},
    "wireless_backhaul_failure_score": {"beta": 1.30, "themes": ["stability_handoff"]},
    "defection_intent_score":     {"beta": 1.50, "themes": ["value_disappointment"]},
    "no_subscription_value_score":{"beta": 0.90, "themes": ["subscription_paywall"]},
    "pro_control_score":          {"beta": 0.80, "themes": ["pro_control_missing"]},
    "vpn_usecase_score":          {"beta": 1.00, "themes": ["vpn_cgnat_block"]},
    "glinet_lockin_score":        {"beta": 1.50, "themes": []},
    "openwrt_control_score":      {"beta": 1.20, "themes": []},
    "iot_pain_score":             {"beta": 0.70, "themes": []},
    "setup_friction_score":       {"beta": 0.30, "themes": ["setup_app_complex"]},
    "brand_lockin_score":         {"beta":-0.40, "themes": []},
    "value_positive_score":       {"beta": 0.50, "themes": []},
    "price_complaint_score":      {"beta":-1.20, "themes": ["value_disappointment"]},
    "discount_dependency_score":  {"beta":-0.80, "themes": []},
    "competitor_substitution_score": {"beta":-0.30, "themes": []}
  },

  "base_logit": -2.20,
  "price_elasticity": -1.5,
  "anchor_node_eur_fallback": 68,

  "sku_track_template": {
    "attack": {
      "label_zh": "攻击轨",
      "price_relative_to_anchor": 0.89,
      "pack_size": 3,
      "target_segments": ["品牌固件失望转投派","入门成效失望退货派"],
      "hero_message": "同价 X 更稳，30 天无理由退"
    },
    "core": {
      "label_zh": "主力轨",
      "price_relative_to_anchor": 1.07,
      "pack_size": 1,
      "target_segments": ["家庭性能 + 安全党","资深 IT 玩家"],
      "hero_message": "3 年使用成本 €X，比 eero 省 €Y"
    },
    "premium": {
      "label_zh": "溢价轨",
      "price_relative_to_anchor": 1.32,
      "pack_size": 1,
      "target_segments": ["多网络安全 / VPN / Pro 玩家"],
      "hero_message": "对位品牌 X 的 50%/70%/N% 价位，3 节点 mesh"
    }
  }
}
```

## 字段说明（核心 11 组）

### 1. `category_id` / `category_label` / `category_label_en`

唯一标识 + 显示名。kebab-case，必须能作文件名。

### 2. `currency` / `exchange_to_usd`

报告统一货币（EUR/USD/CNY 等）+ 该货币换算到 USD 的当前汇率（用于 WebSearch 解析美元报价）。

### 3. `default_market`

默认搜索的地区代码列表，影响 WebSearch 关键词构造。

### 4. `psychological_red_lines`

3 条心理价格红线，**直接写进报告的「禁止组合」warning 框**：
- `single_unit_hard_cap`：单件价格上限（如 €100）
- `multi_unit_budget_anchor`：套餐预算锚定（如 €400）
- `total_anger_zone`：总价愤怒区（如 €500）

### 5. `price_points_for_simulation` / `price_point_labels`

Phase 2 价格情景模拟的 4 个价格点（per 单元）+ 中文标签（攻击 / 主力 / 标准 / 上限）。

### 6. `price_bands`

5 个价格分档，用于 Phase 0.5 缺口分析。**boundaries 必须无 overlap，覆盖 0 → ∞**。

### 7. `brand_price_per_unit_eur` / `brand_keywords`

品牌 → 单件价 + 关键词列表。**brand 必须出现在 brand_price 才能被归因到价格分档**。

### 8. `spec_features`

哪些 spec 字段进入 Hedonic 回归。`log: true` 表示该字段先取对数（处理非线性）。

### 9. `own_product_default_spec`

本品规格 PPT 设定的默认值（如果用户不指定）。会被 Phase 0 用来做预测。

### 10. `pain_themes` / `pain_to_solve_weight` / `meshnode_solve`

13-15 个痛点主题：
- `pain_themes`：每个主题的关键词列表（cluster 名 + 样本里出现就归类到该主题）
- `pain_to_solve_weight`：方法三痛点加权用 — 正值 = 该品类的本品能解（加价），负值 = 本品也踩（折让）
- `meshnode_solve`：第四法缺口分析用 — 0-1，本品对该痛的解决能力（如 1.0 = 完美解，0.3 = 部分解）

### 11. `signals` + `base_logit` + `price_elasticity`

Phase 2 logit 模型参数：
- 12-17 个信号，每个有 `beta`（权重）+ `themes`（该信号对应的痛点主题）
- `base_logit`：baseline logit 值（控制 baseline P(buy) 约 10%）
- `price_elasticity`：价格弹性（默认 -1.5，从 Hedonic 推导）

### 12. `sku_track_template`

3 轨 SKU 决策矩阵的模板（攻击/主力/溢价 轨）。price_relative_to_anchor 是该轨价格相对 ANCHOR 的乘数。

## 校验脚本

```bash
python -c "
import json, jsonschema
config = json.load(open('<category>.json'))
schema = json.load(open('references/config-schema.json'))
jsonschema.validate(config, schema)
print('✓ Config valid')
"
```

（schema JSON 文件可选 — 也可手动 review 字段完整性）

## 复用 checklist · 新品类配置

1. **复制最相近的现有配置** → `references/default-configs/<new>.json`
2. **重写 11 组字段**（重点：pain_themes / signals / brand_keywords / brand_price_per_unit）
3. **第一次跑 Phase 0** 验证 R² ≥ 0.7（Hedonic）和三法中位是否合理
4. **跑 Phase 0.5** 看 top 缺口是否符合直觉
5. **跑 Phase 2** 验证 P(buy) 在 5-70% 区间
6. 不合理 → 调 `meshnode_solve` 或 `beta` 重跑
