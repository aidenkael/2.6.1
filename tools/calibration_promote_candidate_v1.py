"""Offline candidate -> validated promotion CLI.

This tool does not import, activate or enable calibration rules.  It verifies the
reviewed replay by re-running Offline Replay V1 from the original inputs, then
writes a new validated package plus a promotion receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from profit_accounting_26.application.calibration_rule_promotion import (  # noqa: E402
    CalibrationRulePackagePromoter,
    PromotionPrecheckError,
)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _write_json_atomic(path: Path, payload: dict) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_bytes_atomic(path, data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote an Agent Calibration Rule Package V1 candidate after reviewed replay verification"
    )
    parser.add_argument("--candidate-package", required=True, type=Path)
    parser.add_argument("--reviewed-replay", required=True, type=Path)
    parser.add_argument("--feedback-manifest", required=True, type=Path)
    parser.add_argument("--baseline-calibration", required=True, type=Path)
    parser.add_argument("--baseline-registry", required=True, type=Path)
    parser.add_argument("--baseline-calibration-version", required=True, type=str)
    parser.add_argument("--approved-by", required=True, type=str)
    parser.add_argument("--approval-note", type=str, default=None)
    parser.add_argument(
        "--approve",
        required=True,
        action="store_true",
        help="explicitly acknowledge that the reviewed replay has been reviewed",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="explicitly accept matched evaluable records whose score degraded",
    )
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifacts = CalibrationRulePackagePromoter().promote(
            candidate_package=args.candidate_package,
            reviewed_replay=args.reviewed_replay,
            feedback_manifest=args.feedback_manifest,
            baseline_calibration=args.baseline_calibration,
            baseline_registry=args.baseline_registry,
            baseline_calibration_version=args.baseline_calibration_version,
            approved_by=args.approved_by,
            acknowledge_reviewed_replay=args.approve,
            allow_degraded=args.allow_degraded,
            approval_note=args.approval_note,
        )
    except (PromotionPrecheckError, ValueError) as exc:
        print(f"promotion failed: {exc}")
        return 1

    _write_bytes_atomic(args.output_package, artifacts.validated_package_bytes)
    _write_json_atomic(args.output_receipt, artifacts.promotion_receipt)

    validation = artifacts.validated_package["validation"]
    print(f"package_id = {artifacts.validated_package['package_id']}")
    print(f"replay_id = {validation['replay_id']}")
    print(
        "validation = "
        f"matched={validation['matched']} improved={validation['improved']} "
        f"unchanged={validation['unchanged']} degraded={validation['degraded']} "
        f"conflicts={validation['conflicts']}"
    )
    print(f"validated_package = {args.output_package}")
    print(f"promotion_receipt = {args.output_receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
