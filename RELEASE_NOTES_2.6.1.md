# Profit-Accounting-2.6.1 Release Notes

## 发布状态

2.6.1 尚未创建最终 release tag。此前发布前验收结果属于更早代码基线；在当前校准基线重置完成后，最终 Windows 发布回归需重新执行。

## 当前校准架构

生产计算由软件确定性引擎负责。校准闭环固定为：

`软件导出 Feedback V2 → Agent 生成 Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 软件导入 → 用户手动启用 → 确定性运行`

Agent 不拥有生产规则的直接激活权。

软件随包只提供：

- `runtime-safety-baseline-v1`：无历史校准样本、无数值规则的中性 builtin；
- `runtime-safety-empty-v1`：`aggregate_rules=[]`、`sample_rules=[]`；
- `PackagingEstimationService` 的确定性物理安全校验和通用 fallback。

新的 Formal Bundle 必须基于当前空基线重新验证和构建。导入默认 inactive；只有包内已验证规则在用户手动启用后才进入生产仲裁。

## 不变边界

本次校准基线清理不改变：

- 冻结的 V1.2 AI Prompt；
- 确定性物流公式；
- 利润公式；
- DB schema；
- 已冻结 UI 布局；
- 商品历史、反馈记录和 API Profile。

## 最终发布

正式 `v2.6.1` tag 暂不创建。待新的校准规则导入/验证工作完成或用户决定冻结当前基线后，再执行最终 Windows 发布回归与版本收口。
