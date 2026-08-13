# SOURCE_PROVENANCE

## 2.6 R2 migration baseline

- source_repository: `aidenkael/EcommerceSkills`
- source_tag: `profit-legacy-freeze-20260728-r2`
- declared_source_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- verified_checkout_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- target_repository: `aidenkael/Profit-Accounting-2.6`
- baseline_branch: `migration/r2-baseline`
- baseline_commit: `ec6794dfebcbf98a8621e323bd520087fa351a2e`

该段只记录软件迁移来源，不再作为当前包装校准数据来源。

## 2.6.1 logistics integration

- authority: `Development rules-2.6.1.md`
- integration_branch: `integration/logistics-ddad3b-2.6.1`
- upstream_repository: `aidenkael/EcommerceSkills`
- upstream_path: `logistics-cost-skill-2.0/`
- pinned_upstream_commit: `ddad3b7486c2afc7de0b266defb3f5dd22028d00`
- adapter_version: `2.6.1-ddad3b-v1`

确定性物流费用仍由软件引擎负责；包装候选由冻结的 V1.2 AI 与本地确定性安全仲裁协调。

## 2026-08-13 calibration baseline reset

当前软件不再携带旧历史校准样本或旧数值规则。

- builtin baseline: `runtime-safety-baseline-v1`
- builtin registry: `runtime-safety-empty-v1`
- bundled aggregate rules: `0`
- bundled sample rules: `0`
- runtime numeric calibration override before Formal Bundle activation: `0`

新的生产规则只能通过：

`Feedback V2 → Candidate → Validator → Offline Replay → Promotion → Formal Runtime Bundle → 软件导入（inactive）→ 用户手动启用`

Formal Bundle 必须基于 `runtime-safety-baseline-v1` 重新验证和构建。旧 Git commit 仍保留历史迁移痕迹，但不属于当前软件树或运行时数据来源。
