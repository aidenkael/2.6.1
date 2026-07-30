# E-stage Release Candidate Test Report

## Environment

- execution_os: Linux sandbox
- available_python: 3.13.5
- required_production_python: 3.11
- PySide6_available: no
- Windows_build_available: no

## Executed

```text
python -m compileall -q src tests tools
PYTHONPATH=src python -m pytest -q
python tools/sensitive_scan.py
```

## Result

```text
41 passed, 1 skipped
0 failed
0 collection errors
```

Skipped test:

- `tests/ui/test_ui_shell.py`：当前沙箱没有 PySide6，属于环境性跳过。

## Coverage focus

- deterministic logistics calculation;
- profit forward and reverse calculations;
- configurable adjustment rules;
- fixed logistics 2.0 adapter boundary;
- unknown structure safety semantics;
- calibration-data-driven packaging candidates;
- external AI/local calibration conflict audit;
- image session and hashing;
- SQLite initial/recalculation/import/feedback snapshots;
- calibration JSON/ZIP validation, activation and rollback;
- record image persistence;
- import conflict protection;
- sensitive information scan.

## Required Windows verification

`verify_release_candidate.bat` must be executed with Python 3.11 and PySide6. It will rerun compile, all tests, offscreen UI smoke test and sensitive scan.
