# Calibration Baseline

当前软件内置校准基线：`runtime-safety-baseline-v1`。

## 内置内容

- 历史校准样本：0
- 内置 aggregate rules：0
- 内置 sample rules：0
- 数值校准覆盖：0
- 保留能力：PackagingEstimationService 物理安全校验、通用 fallback、Formal Bundle 运行入口

## 新规则进入生产的唯一正常路径

`Feedback V2 → Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 软件导入（inactive）→ 人工启用`

新一轮规则建议以当前空基线：

`runtime-safety-baseline-v1`

作为 replay / promotion / bundle 构建基线，以确保评估结果对应当前生产状态。

软件会明确拒绝基于已退役旧校准基线构建的 Formal Bundle，防止旧历史规则重新进入运行时；其他 Formal Bundle 仍必须通过现有完整性、Validator/Promotion 与 validated rule IDs 等正式校验。

## 导入前检查

1. 不直接导入旧 JSON/旧样本集合充当正式规则。
2. 不复用基于已退役 bundled baseline 构建的旧 Formal Bundle。
3. 新规则必须有 Validator、Offline Replay 和 Promotion 产物。
4. 优先使用 `runtime-safety-baseline-v1` 作为新规则的评估基线。
5. 软件导入后先保持 inactive，人工检查版本/规则数量，再手动启用。
6. 启用后做少量已知商品回放，确认 AI → 安全仲裁 → 物流结果符合预期，再扩大使用。
