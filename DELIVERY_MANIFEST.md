# Profit-Accounting-2.6 E-stage Delivery Manifest

本任务以 Development rules-2.6.1.md 为最高需求。

## Delivery identity

- repository: aidenkael/Profit-Accounting-2.6
- branch: feature/e-stage-local-integration
- base_commit: 325aeed00e9a64caf29e8bfd8dc1b90983bac212
- delivery_commit: 134025d1ee684f67806afce6d0254a30f313aa53
- delivery_type: E-stage Windows release-candidate source/progress package
- formal_windows_release: no

## Fixed sources

- R2_source_commit: d0c07d374c9ee61926de9cd3e01b8c35260c8e5c
- logistics_2_0_pinned_commit: ddad3b7486c2afc7de0b266defb3f5dd22028d00
- local_calibration_version: local-calibration-v3-77-samples
- imported_calibration_samples: 77

## Four uploaded inputs

- Profit-Accounting-2.6.zip: a3dffa457d518e8e635075a7cde4692b78cb15599e94023e6b362c674e0b620a
- logistics-cost-skill-2.0(1).zip: 7752b4a754b39a0bd2765c4f9d6e4fa25034aad7de1c08794891cbb53f410045
- Profit-Accounting-UI-Handoff.zip: 317026ba97216efcf6d68f346574d097b08d720948bd66b8bc6b5b739358d15e
- Desktop.zip: d19d9976e0856605146eedf3e4c43c6e8cbe755e55ccb19c09bf67c42f90e89e

## Verified in current environment

- python: 3.13.5 (production target remains Python 3.11)
- pytest: 41 passed, 1 environment skip
- failed: 0
- collection_errors: 0
- compileall: passed
- sensitive_scan: 0 findings
- source_zip_clean_extract_test: passed

The skipped test is the PySide6 UI smoke test because PySide6 is unavailable in the Linux sandbox.

## Human/environment verification still required

1. Windows Python 3.11 + PySide6 UI launch and scaling review.
2. Windows PyInstaller folder build and launch verification.
3. Real visual AI provider/model/API key validation.
4. Edge + 1688 extension communication in the user's logged-in browser environment.

## Packaging exclusions

- .git
- virtual environments
- caches
- build/dist/release outputs
- real databases and user images
- API keys, tokens, cookies and browser profiles
- original uploaded ZIP archives

This package contains the selected and audited v3 calibration data. It does not replace the pinned ddad3b logistics boundary with the older runtime code found in the local logistics archive.
