# SOURCE_PROVENANCE

## 2.6 R2 migration baseline

- source_repository: `aidenkael/EcommerceSkills`
- source_tag: `profit-legacy-freeze-20260728-r2`
- declared_source_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- verified_checkout_commit: `d0c07d374c9ee61926de9cd3e01b8c35260c8e5c`
- target_repository: `aidenkael/Profit-Accounting-2.6`
- baseline_branch: `migration/r2-baseline`
- baseline_commit: `ec6794dfebcbf98a8621e323bd520087fa351a2e`
- migrated_ai_json_examples: `66`

验证结果：来源 checkout Commit 与冻结 Commit 完全一致。R2 迁移未读取浮动 `master`、旧分支或本地未提交内容。

## 2.6.1 logistics integration

- authority: `Development rules-2.6.1.md`
- integration_branch: `integration/logistics-ddad3b-2.6.1`
- upstream_repository: `aidenkael/EcommerceSkills`
- upstream_path: `logistics-cost-skill-2.0/`
- pinned_upstream_commit: `ddad3b7486c2afc7de0b266defb3f5dd22028d00`
- upstream_calibration_base_commit: `15ce7ddd2fc3a9879bd919eb972319905e75604b`
- adapter_version: `2.6.1-ddad3b-v1`

物流关系：`logistics-cost-skill-2.0` 仍是包装算法、校准规则和物流版本发布的唯一开发上游。本仓库只维护应用适配、确定性费用接口、历史快照和兼容回归，不在两边平行修改包装算法。

固定 Commit `ddad3b...` 的关键兼容行为：暂定规则参与时要求复核；柔软突出部件同时受包装状态门禁；外部 AI 冲突时保留原始候选、本地拟调整和最终审计，不静默覆盖 AI；费用公式和代表回放金额不变。

## 2026-07-29 local E-stage integration

- local_base_commit: `325aeed00e9a64caf29e8bfd8dc1b90983bac212`
- development_branch: `feature/e-stage-local-integration`
- ui_handoff: `Profit-Accounting-UI-Handoff.zip`
- raw_ui_assets: `Desktop.zip`
- local_logistics_package: `logistics-cost-skill-2.0(1).zip`
- imported_calibration_file: `calibration/logistics_v2/calibration_all_cleaned_v3.json`
- imported_calibration_samples: `77`
- packaging_service_version: `packaging-estimation-v1`
- imported_calibration_version: `local-calibration-v3-77-samples`

本地物流压缩包未包含固定 `ddad3b...` 安全补丁的完整运行文件与对应测试，因此只作为校准数据与诊断资料来源。正式费用仍由 2.6 确定性引擎计算，固定 `ddad3b...` 适配边界不被本地旧代码覆盖。

详细审计：`docs/LOCAL_INTEGRATION_AUDIT.md`。
