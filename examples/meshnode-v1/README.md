# MeshNode v1 · Example Output

这是 pricing-pipeline skill 在 GL.iNet MeshNode (WiFi 7 mesh router) 项目上的完整运行产出，
作为 skill 输出的样例参考。

## 文件

| 文件 | 用途 |
|---|---|
| `MeshNode_定价综合报告.html` | 给 PM / 管理层的业务报告（44 KB 单文件，浏览器直接打开）|
| `MeshNode_定价方法详解.md` | 给分析师的方法详解 |
| `pricing_outputs/` | 中间产物（CSV / JSON），Phase 4 真实销售校准时复用 |

## 关键数字

- 三法中位：**€205 / 3-pack**（≈ €68 / 节点）
- PPT 主力价：€73 / 节点（=$80 USD）
- 最大市场缺口：**C 段（€150-220）mesh 稳定性**（FRITZ Repeater 6000 + Nest Wifi Pro 都做不好）
- 推荐核心利润 SKU：**Flint + 2 Nodes €285** 撕中价位 mesh 缺口

## 输入数据

源数据约 80 MB（Reddit 痛点 HTML 73 MB + 竞品评论 HTML 3 MB），未纳入仓库。
完整数据由 `customer-persona-clustering` skill 跑出。
