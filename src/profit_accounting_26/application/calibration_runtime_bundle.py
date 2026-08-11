"""Build a formal, data-only calibration runtime bundle from a validated rule package.

The builder is intentionally offline: it does not touch SQLite, Settings,
CalibrationManager or the active PackagingEstimationService.  It verifies that
the validated package and promotion receipt are bound to the exact baseline
calibration and registry files used during replay, then compiles a runtime
registry containing the validated aggregate rules.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from profit_accounting_26.application.calibration_offline_replay import (
    build_candidate_registry,
    load_json_and_hash,
)
from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.calibration_rule_promotion import PROMOTION_VERSION

FORMAL_BUNDLE_VERSION = "Formal Calibration Runtime Bundle V1"
_MANIFEST_NAME = "formal_package_manifest.json"
_RUNTIME_CALIBRATION_NAME = "runtime_calibration.json"
_RUNTIME_REGISTRY_NAME = "packaging_rule_registry_v1.json"
_VALIDATED_PACKAGE_NAME = "validated_rule_package.json"
_PROMOTION_RECEIPT_NAME = "promotion_receipt.json"


class RuntimeBundlePrecheckError(ValueError):
    """Formal runtime bundle cannot be built from the supplied artifacts."""


@dataclass(frozen=True, slots=True)
class FormalRuntimeBundle:
    bundle_bytes: bytes
    manifest: dict[str, Any]
    runtime_calibration: list[dict[str, Any]]
    runtime_registry: dict[str, Any]


def _canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeBundlePrecheckError(f"{field} must be a non-empty string")
    return value.strip()


def _read_runtime_samples(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    source = Path(path)
    try:
        raw = source.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeBundlePrecheckError(f"cannot read baseline calibration JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeBundlePrecheckError(
            "baseline calibration must already be a runtime-compatible top-level sample list"
        )
    samples = [item for item in payload if isinstance(item, dict)]
    if not samples or len(samples) != len(payload):
        raise RuntimeBundlePrecheckError(
            "baseline calibration must be a non-empty list containing only objects"
        )
    return samples, hashlib.sha256(raw).hexdigest()


def _read_registry(path: str | Path) -> tuple[dict[str, Any], str]:
    payload, digest = load_json_and_hash(path)
    if not isinstance(payload, dict):
        raise RuntimeBundlePrecheckError("baseline registry must be a JSON object")
    for key in ("aggregate_rules", "sample_rules"):
        value = payload.get(key)
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise RuntimeBundlePrecheckError(f"baseline registry {key} must be a list of objects")
    return payload, digest


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class CalibrationRuntimeBundleBuilder:
    """Compile one validated package into a self-contained runtime ZIP bundle."""

    def build(
        self,
        *,
        validated_package: str | Path,
        promotion_receipt: str | Path,
        baseline_calibration: str | Path,
        baseline_registry: str | Path,
        baseline_calibration_version: str,
    ) -> FormalRuntimeBundle:
        baseline_version = _nonempty_string(
            baseline_calibration_version, "baseline_calibration_version"
        )

        package, validated_sha256 = load_json_and_hash(validated_package)
        if not isinstance(package, dict):
            raise RuntimeBundlePrecheckError("validated package must be a JSON object")
        validation_result = AgentCalibrationRulePackageValidator().validate(
            package, require_validated=True
        )
        if not validation_result.is_valid:
            detail = "; ".join(
                f"{issue.path}: {issue.message}" for issue in validation_result.issues
            )
            raise RuntimeBundlePrecheckError(f"validated Rule Package V1 required: {detail}")

        receipt, receipt_sha256 = load_json_and_hash(promotion_receipt)
        if not isinstance(receipt, dict):
            raise RuntimeBundlePrecheckError("promotion receipt must be a JSON object")
        if receipt.get("promotion_version") != PROMOTION_VERSION:
            raise RuntimeBundlePrecheckError(
                f"promotion receipt version must equal {PROMOTION_VERSION!r}"
            )

        package_id = _nonempty_string(package.get("package_id"), "package_id")
        calibration_version = _nonempty_string(
            package.get("calibration_version"), "calibration_version"
        )
        validation = package.get("validation")
        if not isinstance(validation, dict):
            raise RuntimeBundlePrecheckError("validated package validation block missing")

        if receipt.get("candidate_package_id") != package_id:
            raise RuntimeBundlePrecheckError("promotion receipt package_id does not match validated package")
        if receipt.get("validated_package_sha256") != validated_sha256:
            raise RuntimeBundlePrecheckError(
                "promotion receipt validated_package_sha256 does not match validated package bytes"
            )
        if receipt.get("reviewed_replay_id") != validation.get("replay_id"):
            raise RuntimeBundlePrecheckError("promotion receipt replay_id does not match validation block")
        if receipt.get("validation_counts") != validation:
            raise RuntimeBundlePrecheckError("promotion receipt validation_counts do not match package validation")

        receipt_baseline_version = receipt.get("baseline_calibration_version")
        package_baseline_version = validation.get("baseline_calibration_version")
        declared_base_version = package.get("base_calibration_version")
        if receipt_baseline_version != baseline_version or package_baseline_version != baseline_version:
            raise RuntimeBundlePrecheckError(
                "baseline calibration version does not match promotion receipt / validation block"
            )
        if declared_base_version and declared_base_version != baseline_version:
            raise RuntimeBundlePrecheckError(
                "validated package base_calibration_version does not match supplied baseline version"
            )

        coverage = receipt.get("rule_coverage")
        if not isinstance(coverage, dict) or coverage.get("uncovered_rule_ids") != []:
            raise RuntimeBundlePrecheckError("promotion receipt must show complete rule coverage")

        samples, baseline_calibration_sha256 = _read_runtime_samples(baseline_calibration)
        registry, baseline_registry_sha256 = _read_registry(baseline_registry)
        fingerprints = receipt.get("input_fingerprints")
        if not isinstance(fingerprints, dict):
            raise RuntimeBundlePrecheckError("promotion receipt input_fingerprints missing")
        if fingerprints.get("baseline_calibration_sha256") != baseline_calibration_sha256:
            raise RuntimeBundlePrecheckError(
                "baseline calibration bytes differ from the replay-validated baseline"
            )
        if fingerprints.get("baseline_registry_sha256") != baseline_registry_sha256:
            raise RuntimeBundlePrecheckError(
                "baseline registry bytes differ from the replay-validated baseline"
            )

        runtime_registry = build_candidate_registry(copy.deepcopy(registry), package)
        runtime_registry["version"] = calibration_version

        runtime_calibration_bytes = _canonical_json_bytes(samples)
        runtime_registry_bytes = _canonical_json_bytes(runtime_registry)
        validated_package_bytes = Path(validated_package).read_bytes()
        promotion_receipt_bytes = Path(promotion_receipt).read_bytes()

        enabled_rule_ids = [
            str(rule.get("rule_id"))
            for rule in package.get("rules", [])
            if isinstance(rule, dict) and rule.get("enabled") is True
        ]
        manifest = {
            "contract_version": FORMAL_BUNDLE_VERSION,
            "package_id": package_id,
            "calibration_version": calibration_version,
            "engine_version": validation.get("engine_version"),
            "baseline_calibration_version": baseline_version,
            "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "files": {
                "runtime_calibration": _RUNTIME_CALIBRATION_NAME,
                "runtime_registry": _RUNTIME_REGISTRY_NAME,
                "validated_rule_package": _VALIDATED_PACKAGE_NAME,
                "promotion_receipt": _PROMOTION_RECEIPT_NAME,
            },
            "source_fingerprints": {
                "validated_rule_package_sha256": validated_sha256,
                "promotion_receipt_sha256": receipt_sha256,
                "baseline_calibration_sha256": baseline_calibration_sha256,
                "baseline_registry_sha256": baseline_registry_sha256,
            },
            "runtime_fingerprints": {
                "runtime_calibration_sha256": _sha256_bytes(runtime_calibration_bytes),
                "runtime_registry_sha256": _sha256_bytes(runtime_registry_bytes),
            },
            "runtime_summary": {
                "sample_count": len(samples),
                "aggregate_rule_count": len(runtime_registry.get("aggregate_rules", [])),
                "sample_rule_count": len(runtime_registry.get("sample_rules", [])),
                "validated_rule_ids": enabled_rule_ids,
            },
        }
        manifest_bytes = _canonical_json_bytes(manifest)
        bundle_bytes = _zip_bytes(
            {
                _MANIFEST_NAME: manifest_bytes,
                _RUNTIME_CALIBRATION_NAME: runtime_calibration_bytes,
                _RUNTIME_REGISTRY_NAME: runtime_registry_bytes,
                _VALIDATED_PACKAGE_NAME: validated_package_bytes,
                _PROMOTION_RECEIPT_NAME: promotion_receipt_bytes,
            }
        )
        return FormalRuntimeBundle(
            bundle_bytes=bundle_bytes,
            manifest=manifest,
            runtime_calibration=samples,
            runtime_registry=runtime_registry,
        )


def build_runtime_bundle(
    *,
    validated_package: str | Path,
    promotion_receipt: str | Path,
    baseline_calibration: str | Path,
    baseline_registry: str | Path,
    baseline_calibration_version: str,
) -> FormalRuntimeBundle:
    return CalibrationRuntimeBundleBuilder().build(
        validated_package=validated_package,
        promotion_receipt=promotion_receipt,
        baseline_calibration=baseline_calibration,
        baseline_registry=baseline_registry,
        baseline_calibration_version=baseline_calibration_version,
    )
