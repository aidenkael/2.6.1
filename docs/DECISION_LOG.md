# DECISION_LOG

> 状态：2.6.1 物流接入边界已锁定。阶段 0 与 R2 迁移决定继续有效；本文件新增固定 `ddad3b...` 来源及三层职责边界。

| ID | 决定 | 依据 | 处理结果 | 是否需再问用户 |
|---|---|---|---|---|
| DEC-001 | R2 唯一来源 | 冻结声明与迁移清单均指定 `profit-legacy-freeze-20260728-r2` | 所有迁移从该标签读取，不从浮动 `master` 或旧分支读取 | 否 |
| DEC-002 | R2 Commit | GitHub 已存在 `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`，提交信息为 `chore: finalize legacy freeze r2 baseline` | 写入全部来源与迁移报告 | 否 |
| DEC-003 | 最终报告占位文字 | R2 `final_report.md` 中 master SHA 与推送状态仍有任务前占位，但标签和 Commit 已实际存在，冻结/迁移文档已修正 | 以实际标签、Commit、LEGACY_FREEZE 和 MIGRATION_SOURCE_MANIFEST 为准；不把占位当冲突 | 否 |
| DEC-004 | 旧利润项目冻结 | `Profit accounting-Auto` 只允许迁移取证和文档修正 | 不再扩展旧 Tkinter 项目，所有新功能进入独立仓库 `aidenkael/Profit-Accounting-2.6` | 否 |
| DEC-005 | 物流唯一上游 | `logistics-cost-skill-2.0` 是唯一开发源 | 2.6 只导入发布版本，不平行修改算法 | 否 |
| DEC-006 | UI 基准替换 | 本次上传两张图是最新最高视觉基准 | 复制为 `new_product_calculation.png` 与 `settings.png`；旧 1.5 单图仅作历史参考 | 否 |
| DEC-007 | 示例值非业务值 | 当前提示明确人物、商品、金额、版本号是示例 | “张三”、v1.5.0、目录、金额、更新时间等均由真实数据替换 | 否 |
| DEC-008 | 货代归档而非硬删除 | 设置图显示“归档/删除”，本次明确要求“归档/恢复”，且历史需稳定 ID | 活跃货代显示“归档”；已归档显示“恢复”；第一版不硬删除有历史引用的货代 | 否，当前提示已确认 |
| DEC-009 | 尾程费用位置 | 1.5 曾允许货代配置尾程，最新 UI 和提示把默认尾程放在基础设置，货代表不显示尾程列 | 2.6 第一版使用全局默认尾程费用；不在货代表新增尾程字段 | 否，当前提示优先 |
| DEC-010 | 货代排序 | 1.5 提到排序，最新设置图和明确清单未包含排序控件 | 第一版按稳定内部顺序展示，不新增可见排序控件 | 否 |
| DEC-011 | 设置页额外卡片 | 1.5 提到 AI 服务商、API Key、备份恢复，最新设置页锁定为基础设置、货代、利润规则 | 阶段 0 不加入额外设置卡；后续需要时必须走 UI 偏差确认 | 否 |
| DEC-012 | 核价输入 | 1.5 与本次提示均确认 SHEIN 核价手动输入 | 不识别核价截图，不新增核价图片类型 | 否 |
| DEC-013 | AI 与计算边界 | 视觉 AI 只识别和估算包装，费用与利润由本地确定性程序计算 | AI 不决定汇率、货代费率、体积重公式、总成本、利润或货代选择 | 否 |
| DEC-014 | 包装双档 | 两张 UI 和总规均要求正常档与保守档同时展示 | 两档可编辑，用户选择当前采用档；默认正常档 | 否 |
| DEC-015 | 旧数据库 | 冻结声明明确 2.6 不要求直接兼容旧 Tkinter 数据库 | 不直接依赖或迁移旧库；真实记录以后受控导入 | 否 |
| DEC-016 | 三份 R2 外 AI JSON | 本次提示明确 `airpods_case`、`folding_sunglasses`、`seatbelt_extender` 未进入 R2 | 不放入迁移基线，进入下一轮独立校准 | 否 |
| DEC-017 | 阶段 0 文件范围 | 总控提示要求 UI_BASELINE 和 UI_DEVIATION_REGISTER，用户消息列出其余五份 | 生成完整 7 份文档与 2 张 UI 图片，不省略总控要求 | 否 |
| DEC-018 | 当前关键冲突 | 权威来源中不存在无法按优先级消解、会改变业务规则或 UI 的冲突 | 关键问题为“无”，等待用户只确认阶段 0 | 否 |
| DEC-019 | 2.6.1 最高准则 | 用户明确要求生成 2.6.1 并作为项目新的最高准则 | `Development rules-2.6.1.md` 继承并覆盖 2.6；以后使用新暗号 | 否 |
| DEC-020 | 固定物流接入 Commit | 用户明确指定 `ddad3b7486c2...`；GitHub 核对完整 SHA 为 `ddad3b7486c2afc7de0b266defb3f5dd22028d00` | 本轮只读取该完整 Commit，不读取浮动 master | 否 |
| DEC-021 | AI 能力与权限分离 | 最新讨论确认脚本不应限制 AI 推理能力，但 AI 不能拥有费用和最终采用权 | AI 可输出丰富事实与正常/保守包装候选；费用字段越权，必须拒绝 | 否 |
| DEC-022 | 包装估算层独立 | 固定 Commit 提供证据仲裁、包装校准、软品安全门和冲突审计 | 2.6 适配层接收包装输出，不复制或平行演化包装算法 | 否 |
| DEC-023 | 确定性物流引擎边界 | 当前 2.6 `calculate_logistics` 已按 PackageSpec、Forwarder 和尾程计算 | 只根据已采用包装和动态货代配置计算，不调用 AI，不修改包装 | 否 |
| DEC-024 | 外部 AI 冲突不静默覆盖 | `ddad3b...` 明确保留 AI 原始、本地拟调整、最终方案及规则审计 | 适配层完整透传审计元数据，用户或上层决定采用值 | 否 |
| DEC-025 | 兼容默认值不是生产真实值 | 上游为旧 JSON 回放保留默认尺寸/重量并标记 `default_fields_used` | 关键默认值未被人工替换时，2.6 阻止正式采用并显示待补充 | 否 |
| DEC-026 | 物流接入分支 | 用户要求从 2.6 R2 基线建立分支 | 从 `ec6794df...` 建立 `integration/logistics-ddad3b-2.6.1` | 否 |
| DEC-027 | AI/本地职责永久边界 | 83 条校准收口后用户固定职责边界 | AI 负责产品名/observed/bare_estimate/quantity/shipment/最小 structure；本地只做保护与已验证确定性修正，不做第二套包装判断 | 否 |
| DEC-028 | 本地介入白名单 | 完整合法 AI shipment 默认通过，仅四类可介入 | 用户确认事实、页面/商家硬事实、83 条 validated 保护规则、validated 数值规则；软语义冲突只记录 warning + needs_review | 否 |
| DEC-029 | generic 兜底退出生产 | 固定 25×18×5 等兜底与固定压缩率被用户禁止 | PackagingEstimationService 不再以 generic_candidate 覆盖完整 AI shipment；AI 缺失时优先人工补充复核 | 否 |
| DEC-030 | RecognitionOutcome 合同 | `last_raw_proposal` 是临时状态共享，用户要求最小明确结果合同 | 新增 RecognitionOutcome（raw_observation/raw_ai_proposal/adopted_proposal/arbitration_observation/arbitration_trace），UI 不再反向读取服务状态 | 否 |
| DEC-031 | confirmed_facts 先于仲裁 | 用户确认裸重 700g 必须参与本地仲裁而非事后覆盖 | RuntimeRecognitionService 复制 raw_observation 后先应用 confirmed_facts，再进 PackagingEstimationService；raw 历史永不被污染 | 否 |
| DEC-032 | 历史四层语义 | 用户要求 ai_initial / initial_adopted(local) / user_current / actual | 复用 SQLite + `_v2`：ai_initial 冻结 raw+confirmed_facts；adopted_packaging 记录本地仲裁；current_estimate 为当前采用；feedback actual_logistics 为真实物流；旧记录兼容读取 | 否 |
| DEC-033 | manifest 四层 | Excel 保持 7 列，manifest machine_facts 区分 AI/local/user/actual | machine_facts 含 ai_initial / local_adopted / user_feedback / actual_logistics | 否 |
| DEC-034 | Prompt v1.8 收口 | 用户要求"短，但 AI 看得懂"，恢复一行销售单位逻辑，structure 一行词表 | v1.8：purchase_quantity 未知→quantity_source=assumed/unknown；packing_actions 仅正式允许值；rigidity/foldability/compressibility 一行词表 | 否 |

## 未决事项

当前无需要改变 UI 或业务规则的未决事项。真实视觉 API 的具体供应商和凭据配置仍按 2.6 原规则延后，未进入本轮 UI。
