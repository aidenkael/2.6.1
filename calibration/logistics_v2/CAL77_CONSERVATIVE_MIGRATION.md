# CAL77 Conservative Migration V1

- 日期：2026-08-12
- `calibration_all_cleaned_v3.json` 77 条历史样本字节级未修改（档案保留）。
- `packaging_rule_registry_v1.json` 升级为 `packaging-rules-v2-cal77-conservative`：
  - 77 条 sample_rules 全部 `enabled=false`，退出 runtime（role 等历史字段保持原语义）。
  - 仅 `AGR-THIN-TEXTILE-001` 保留为低置信 legacy numeric fallback（`confidence=low`、`needs_review=true`，action 参数不变）。
  - 其余 8 条 aggregate 全部 `enabled=false`，附 `migration_status` / `migration_reason` 作为历史参考。
- 所有 CAL77 证据均为 freight-inferred，不满足新闭环真实包装 truth 口径。
- 新反馈统一走 Formal calibration closed loop：
  Feedback V2 → Candidate → Validator → Offline Replay → Promotion → Formal Bundle → 用户启用。
- `PackagingEstimationService`、DB schema、UI、物流公式均未修改。
