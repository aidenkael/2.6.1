"""Build a Formal Calibration Runtime Bundle V1 ZIP without importing or activating it."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from profit_accounting_26.application.calibration_runtime_bundle import (  # noqa: E402
    CalibrationRuntimeBundleBuilder,
    RuntimeBundlePrecheckError,
)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build formal calibration runtime bundle v1")
    parser.add_argument("--validated-package", required=True, type=Path)
    parser.add_argument("--promotion-receipt", required=True, type=Path)
    parser.add_argument("--baseline-calibration", required=True, type=Path)
    parser.add_argument("--baseline-registry", required=True, type=Path)
    parser.add_argument("--baseline-calibration-version", required=True, type=str)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = CalibrationRuntimeBundleBuilder().build(
            validated_package=args.validated_package,
            promotion_receipt=args.promotion_receipt,
            baseline_calibration=args.baseline_calibration,
            baseline_registry=args.baseline_registry,
            baseline_calibration_version=args.baseline_calibration_version,
        )
    except (RuntimeBundlePrecheckError, ValueError) as exc:
        print(f"runtime bundle build failed: {exc}")
        return 1

    _write_bytes_atomic(args.output, bundle.bundle_bytes)
    summary = bundle.manifest["runtime_summary"]
    print(f"package_id = {bundle.manifest['package_id']}")
    print(f"calibration_version = {bundle.manifest['calibration_version']}")
    print(
        "runtime = "
        f"samples={summary['sample_count']} aggregate_rules={summary['aggregate_rule_count']} "
        f"sample_rules={summary['sample_rule_count']}"
    )
    print(f"output = {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
