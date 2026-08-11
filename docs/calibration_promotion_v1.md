# Calibration Promotion V1

用途：将已经通过 Offline Replay V1 审阅的 Agent Calibration Rule Package V1 `candidate`，由软件生成新的 `validated` 包。

核心边界：

- candidate 原文件保持不变；
- promotion 会使用原始输入重新执行 Offline Replay V1，并与已审阅 replay 逐字段比对，仅忽略随机 `replay_id`；
- 每条启用规则必须至少在一条“实际 applied 且有可评估真实包装 truth”的记录上得到覆盖；
- 不设置改善率、未命中率等数值晋级阈值；
- 如果存在 degraded 的 matched/evaluable 记录，默认拒绝，只有显式确认 `allow_degraded` 后才能继续；
- validated package 继续严格使用现有 Agent Calibration Rule Package V1，不修改其 Schema；
- 另生成 promotion receipt，记录审批人、replay、输入指纹、validated package SHA-256 和规则覆盖情况；
- 本工具不导入、不启用、不修改当前 active calibration，也不操作 CAL77。

Validation block 中的 `matched / improved / unchanged / degraded` 只统计“candidate 规则真实 applied 且有可评估 truth”的记录，因此满足 V1 合同要求：

`improved + unchanged + degraded == matched`

Replay summary 本身保留原有更宽的统计语义，不被 promotion 修改。
