# Agent Calibration Rule Package V1 — Review Notes

本文件记录从 Stage 4 后设计审计中保留的关键结论，防止后续实现偏离合同。

1. 当前 `CalibrationManager.import_package()` 只接受旧样本型 calibration JSON/ZIP；V1 不能直接生产导入。
2. 当前 `PackagingEstimationService` 的 aggregate rule 动作只有：`smallest_axis_scale`、`smallest_axis_add`、`volume_ratio`、`reference_scaled_template`。
3. `smallest_axis_add` 当前只能调整最短轴，字段为 `normal_cm` / `conservative_cm`；不支持 `axis` / `value_cm`。
4. Agent 只生成 `candidate`；`validated` 必须由未来的软件侧 validator + offline replay 晋级。
5. 不在 V1 先验写死 replay 晋级阈值；阈值需用真实反馈数据确定。
6. 不在本阶段处理 CAL77 retain / migrate / delete。
