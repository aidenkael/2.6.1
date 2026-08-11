"""Offline Replay V1 CLI：只做离线读取与输出，不修改生产数据。

用法：
    python tools/calibration_offline_replay_v1.py \
        --feedback-manifest 校准反馈_xxxx/manifest.json \
        --candidate-package  candidate_package.json \
        --baseline-calibration calibration_all_cleaned_v3.json \
        --baseline-registry    packaging_rule_registry_v1.json \
        --output               replay_result.json

安全边界：
- 不调用 activate()、不写 CalibrationManager / calibration_packages / builtin /
  CAL77 / 数据库 / Settings；
- candidate 只临时叠加到 registry aggregate_rules（保留 sample_rules），
  临时目录用后自动清理；
- 冲突或预检失败时停止正式 replay，不自动生成 validated 包。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from profit_accounting_26.application.calibration_offline_replay import (  # noqa: E402
    REPLAY_VERSION,
    OfflineCalibrationReplay,
    ReplayConflictError,
    ReplayPrecheckError,
)
from profit_accounting_26.application.packaging_estimation_service import (  # noqa: E402
    PackagingEstimationService,
)


def _conflict_output(conflicts: list) -> dict:
    return {
        "replay_version": REPLAY_VERSION,
        "replay_id": uuid4().hex,
        "candidate_package_id": None,
        "engine_version": PackagingEstimationService.ENGINE_VERSION,
        "baseline_calibration_version": None,
        "summary": {
            "total_records": 0,
            "evaluable_records": 0,
            "insufficient_truth": 0,
            "skipped_ai_initial_missing": 0,
            "matched": 0,
            "unmatched": 0,
            "improved": 0,
            "unchanged": 0,
            "degraded": 0,
            "conflicts": len(conflicts),
        },
        "conflicts": [conflict.to_dict() for conflict in conflicts],
        "largest_degradations": [],
        "per_record": [],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calibration Offline Replay V1 (read-only)")
    parser.add_argument("--feedback-manifest", required=True, type=Path, help="Calibration Feedback Export V2 manifest.json")
    parser.add_argument("--candidate-package", required=True, type=Path, help="Agent Calibration Rule Package V1 candidate JSON")
    parser.add_argument("--baseline-calibration", required=True, type=Path, help="baseline calibration samples JSON")
    parser.add_argument("--baseline-registry", required=True, type=Path, help="baseline packaging_rule_registry_v1.json")
    parser.add_argument("--output", required=True, type=Path, help="output replay_result.json path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = OfflineCalibrationReplay().run(
            feedback_manifest=args.feedback_manifest,
            candidate_package=args.candidate_package,
            baseline_calibration=args.baseline_calibration,
            baseline_registry=args.baseline_registry,
        )
    except ReplayConflictError as exc:
        _write_json(args.output, _conflict_output(exc.conflicts))
        print(f"offline replay stopped by {len(exc.conflicts)} conflict(s); see {args.output}")
        for conflict in exc.conflicts:
            print(f"- [{conflict.code}] {conflict.message}")
        return 1
    except ReplayPrecheckError as exc:
        print(f"offline replay precheck failed: {exc}")
        return 1
    except ValueError as exc:
        print(f"offline replay failed: {exc}")
        return 1
    _write_json(args.output, result)
    summary = result["summary"]
    print(f"replay_id = {result['replay_id']}")
    print(
        "summary = "
        f"total={summary['total_records']} evaluable={summary['evaluable_records']} "
        f"insufficient_truth={summary['insufficient_truth']} matched={summary['matched']} "
        f"unmatched={summary['unmatched']} improved={summary['improved']} "
        f"unchanged={summary['unchanged']} degraded={summary['degraded']} "
        f"conflicts={summary['conflicts']}"
    )
    print(f"output = {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
