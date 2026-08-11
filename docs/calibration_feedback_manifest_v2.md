# Calibration Feedback Export manifest V2

## 用途

`manifest.json` 从面向人类摘要的 V1 升级为可供后续 Agent 分析 / offline replay
使用的机器可读事实 V2：`CONTRACT_VERSION = "Calibration Feedback Export V2"`。

offline replay 的 baseline 必须由软件同一 `PackagingEstimationService` 重新计算，
因此 V2 不导出任何历史 `current_estimate` / 计算快照，只导出可复现的输入事实。

## 顶层结构（不变）

```json
{
  "contract_version": "Calibration Feedback Export V2",
  "export_batch_id": "...",
  "exported_at": "...",
  "records": [...]
}
```

每条 record 保留 V1 人类可读字段（`sequence` / `record_id` /
`product_short_name` / `product_link` / `main_image` / `images` /
`ai_initial_shipment` / `user_calibration` / `actual_first_mile`），
并新增 `machine_facts`。

## machine_facts 两层

```json
"machine_facts": {
  "ai_initial": { ... },
  "user_feedback": { ... }
}
```

- `ai_initial`：只从真正首次 AI 快照 `_v2.ai_initial` 读取。`observation` 与
  raw evidence（`field_evidence` / `confirmed_facts` / `shipment`）按包装白名单
  过滤；`packaging_proposal` 优先 `external_ai_packaging_proposal`，缺失时回退
  `ai_initial.adopted_packaging`（均为首次快照内历史值）。旧记录或
  `legacy_layers_ai_raw` 不伪装成首次 AI 事实，输出 `null`。
- `user_feedback`：直接读取 linked `CalibrationFeedback` 的 `structure` /
  `suggested_package` / `actual_logistics` / `user_note` 等精确字段；
  `suggested_package.evidence_level` 恒为 `user_suggested`，
  实际费用与真实包装尺寸各自保留原值，不互相推导。

缺失对象使用 `null`，列表使用 `[]`；不猜测、不反推。

## 禁止字段

manifest 全文（含嵌套）不得出现：

- `current_estimate` / `calculation_snapshot` / `profit_scenarios`；
- 采购与国内运费：`product_cost_rmb`、`product_cost_value_type`、
  `domestic_shipping_rmb`、`domestic_shipping_value_type`；
- 成本与汇率：`system_cost_rmb`、`exchange_rate`；
- 售价区：`sale_price_usd`、`sale_price_rmb`；
- 利润区：`profit_rmb`、`profit_usd`、`profit_rate`；
- 其它：`subsidy`、`tail_fee_rmb`、`shein_quote_usd` 及同类经济字段。

V2 允许并需要包装尺寸/重量字段：`length_cm`、`width_cm`、`height_cm`、`weight_g`。

## Excel 不变

`校准反馈.xlsx` 的 Sheet1 仍严格 7 列（序号 / 商品简名 / 商品链接 / 图片 /
AI首次发货估算 / 用户校准内容 / 真实头程），Sheet2 技术元数据结构不变。
