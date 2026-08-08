# 历史记录与校准数据合同 V1（Data Foundation）

日期：2026-08-08 · 分支：`feat/history-calibration-data-foundation` · 基线：main @ 9cc9269

本文档定义四个数据合同的职责边界。本轮只做后端数据能力，不做 UI；不改 AI、CAL77、包装/物流/利润公式。

## 1. HistoryRecord V2（`history-record-v2`）

实现：`application/data_contracts.py::HistoryRecordV2` + `application/history_record_service.py`

**存储策略**：不建第二套数据库。V2 字段以附加键 `_v2` 写入现有 `records.payload_json`；旧记录无 `_v2` 键时由 `record_from_payload()` 给出兼容视图（V2 字段默认 null，AI 原始输出以 `legacy_layers_ai_raw` 近似映射，`current_estimate` 从被采纳档位派生）。零不可逆迁移。

**字段分组**：

| 分组 | 字段 | 说明 |
|---|---|---|
| Identity | record_id / record_schema_version / created_at / updated_at / revision / origin | origin 仅 `new_calculation` \| `history_edit` |
| Product | product_name / product_link / sku / quantity | |
| Images | images | 只存 ImageStore 引用（image_id/sha256/storage_key），不存二进制 |
| Bare Facts | bare_product | 裸品事实，与包装推断严格分开 |
| Initial AI | ai_initial | provider / model / prompt_version / engine_version / observation / estimated_package / legacy_packaging_output；**只在新建时写入，编辑绝不覆盖** |
| Current | current_estimate | 单一主结果（未来 AI V2 单值输出的挂载点） |
| Calculation | calculation_snapshot | 复用现有 profit_scenarios / layers.calculated |
| Feedback | calibration_feedback_id | 只存引用，反馈本体在 calibration_feedback 表 |

**修改语义**：新测算 → `create_record`（revision=1）；历史恢复编辑 → `update_record`（同 record_id，revision+1，origin=history_edit，旧 `_v2` 块自动保留）。`link_feedback` 只挂引用、不改 revision。

## 2. ImageStore V1

实现：`storage/image_store.py`（`images` 表，CREATE TABLE IF NOT EXISTS）

- 内容寻址：SHA256 去重，同字节只存一份；原图 + 缩略图（QImage 240px JPG，失败安全降级为无缩略图）。
- 路径：遵循 `ApplicationPaths.data_dir`，`images/originals/<hash[:2]>/<hash><suffix>` 与 `images/thumbnails/…`；数据库只存相对 storage key，不硬编码绝对路径。
- 删除安全：`is_referenced()` 按 image_id / sha256 / storage_key 扫描历史记录引用（兼容旧 `relative_path` 格式）。**删除记录 ≠ 删除图片**；本轮不做垃圾回收。

## 3. CalibrationFeedback V1（`calibration-feedback-v1`）

实现：`application/calibration_feedback_service.py`（`calibration_feedback` 表）

- 身份：feedback_id / feedback_schema_version / record_id / source（`user` \| `developer`）。
- 结构反馈：五个三态字段（can_fold / can_compress / can_coil / can_disassemble / requires_shape_retention，true/false/unknown）+ 五种 parts 列表 + axis_behavior（length/width/height × preserve/fold/compress/coil/unknown）。
- 建议包装：suggested_package 证据等级恒为 `user_suggested`，绝不标 measured。
- 实际物流：全可选；0 是合法值（≠ 缺失）；实际费用不得反推真实包装尺寸。
- user_note 保留用户原文。
- **保存原则**：只有文字、只有单个结构标记、没有真实头程都可以保存；只有空反馈和非法枚举才拒绝。
- **防重复导出状态**：calibration_exported_at / calibration_export_batch_id / feedback_updated_after_export，只做状态记录，不阻止再次保存或导出。

## 4. 导出（仅后端）

实现：`application/history_export_service.py`

| 导出 | 格式标识 | 内容 |
|---|---|---|
| Full History Export | `history-export-v1.zip` | manifest.json / records.json / feedback.json；include_images 默认 false |
| Calibration Export | `calibration-feedback-v1.zip` | manifest.json / feedback.json / records_summary.json；manifest 含 model / prompt_version / rule / software 版本 |

- 范围（range）：all / record_ids / created_at_range / updated_at_range；可叠加 `unexported_calibration_only`。
- 脱敏：递归剥离 api_key/authorization/token 等键名、data URL、绝对路径（取 basename）；写出前正则复扫，发现疑似密钥即 `ExportAbortError` 中止（不产生文件）。
- ZIP 安全：拒绝 `..`、绝对路径、盘符；include_images 时只允许 data_dir 内文件。
- Calibration 导出成功后自动 `mark_exported(batch_id)`。

## 边界（本轮不做）

历史记录 UI、用户反馈 UI、AI V2 算法、Rule V2、自动学习、图片 GC、上传/云同步。
