"""Formal Calibration Runtime Bundle V1 — import-time validation.

This module is offline and side-effect-free.  It validates a ZIP that claims
to be a Formal Calibration Runtime Bundle V1, extracting and verifying every
fixed member.  It does NOT import, activate, or touch the database.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.calibration_rule_promotion import PROMOTION_VERSION
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService

FORMAL_BUNDLE_VERSION = "Formal Calibration Runtime Bundle V1"

_REQUIRED_MEMBERS = (
    "formal_package_manifest.json",
    "runtime_calibration.json",
    "packaging_rule_registry_v1.json",
    "validated_rule_package.json",
    "promotion_receipt.json",
)

# manifest.files 必须严格映射到这些文件名
_EXPECTED_FILES_MAP = {
    "runtime_calibration": "runtime_calibration.json",
    "runtime_registry": "packaging_rule_registry_v1.json",
    "validated_rule_package": "validated_rule_package.json",
    "promotion_receipt": "promotion_receipt.json",
}

MAX_JSON_BYTES = 20 * 1024 * 1024


class FormalBundleValidationError(ValueError):
    """The ZIP is not a valid Formal Calibration Runtime Bundle V1."""


@dataclass(frozen=True, slots=True)
class ValidatedFormalBundle:
    """All validated artefacts extracted from a formal bundle ZIP."""

    manifest: dict[str, Any]
    runtime_calibration: list[dict[str, Any]]
    runtime_registry: dict[str, Any]
    validated_package: dict[str, Any]
    promotion_receipt: dict[str, Any]
    member_bytes: dict[str, bytes] = field(repr=False)
    zip_sha256: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FormalBundleValidationError(f"{label}: cannot parse JSON: {exc}") from exc


def _is_root_level_member(name: str) -> bool:
    """检查 ZIP 成员是否在根目录（不含路径分隔符）。"""
    if name.endswith("/"):
        return False
    pure = PurePosixPath(name)
    # 根目录成员：PurePosixPath 只有 name，没有 parent parts
    return len(pure.parts) == 1


def validate_formal_bundle_zip(zip_path: str | Path) -> ValidatedFormalBundle:
    """Open a ZIP, detect formal bundle, validate all members and return artefacts.

    Raises ``FormalBundleValidationError`` on any problem.
    """
    source = Path(zip_path)
    zip_bytes = source.read_bytes()
    zip_sha = _sha256(zip_bytes)

    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise FormalBundleValidationError(f"ZIP is corrupt: {exc}") from exc

    with archive:
        # ── security: path traversal, duplicates ──
        names_seen: set[str] = set()
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise FormalBundleValidationError(f"unsafe path in ZIP: {name}")
            if name.endswith("/"):
                continue
            if name in names_seen:
                raise FormalBundleValidationError(f"duplicate ZIP member: {name}")
            names_seen.add(name)

        # ── detect formal bundle: manifest must be at ROOT level ──
        root_members = {name for name in names_seen if _is_root_level_member(name)}
        if "formal_package_manifest.json" not in root_members:
            raise FormalBundleValidationError("not a formal bundle (missing formal_package_manifest.json at root)")

        # ── require all fixed members at ROOT level ──
        for member in _REQUIRED_MEMBERS:
            if member not in root_members:
                raise FormalBundleValidationError(f"missing required member at root: {member}")

        # ── read raw bytes (exact root-level names only) ──
        member_bytes: dict[str, bytes] = {}
        for member in _REQUIRED_MEMBERS:
            raw = archive.read(member)
            if len(raw) > MAX_JSON_BYTES:
                raise FormalBundleValidationError(f"{member}: exceeds {MAX_JSON_BYTES} bytes")
            member_bytes[member] = raw

    # ── parse JSON ──
    manifest = _read_json(member_bytes["formal_package_manifest.json"], "manifest")
    runtime_cal = _read_json(member_bytes["runtime_calibration.json"], "runtime_calibration")
    runtime_reg = _read_json(member_bytes["packaging_rule_registry_v1.json"], "registry")
    validated_pkg = _read_json(member_bytes["validated_rule_package.json"], "validated_package")
    receipt = _read_json(member_bytes["promotion_receipt.json"], "promotion_receipt")

    # ── manifest contract ──
    if not isinstance(manifest, dict):
        raise FormalBundleValidationError("manifest must be a JSON object")
    if manifest.get("contract_version") != FORMAL_BUNDLE_VERSION:
        raise FormalBundleValidationError(
            f"manifest contract_version must be {FORMAL_BUNDLE_VERSION!r}, "
            f"got {manifest.get('contract_version')!r}"
        )

    # ── manifest fields ──
    for key in ("package_id", "calibration_version", "engine_version", "baseline_calibration_version"):
        val = manifest.get(key)
        if not isinstance(val, str) or not val.strip():
            raise FormalBundleValidationError(f"manifest.{key} must be a non-empty string")
    for key in ("files", "source_fingerprints", "runtime_fingerprints", "runtime_summary"):
        if not isinstance(manifest.get(key), dict):
            raise FormalBundleValidationError(f"manifest.{key} must be an object")

    # ── manifest.files 严格映射验证 ──
    files_map = manifest["files"]
    for logical_name, expected_filename in _EXPECTED_FILES_MAP.items():
        actual = files_map.get(logical_name)
        if actual != expected_filename:
            raise FormalBundleValidationError(
                f"manifest.files.{logical_name} must be {expected_filename!r}, got {actual!r}"
            )

    # ── SHA-256 verification ──
    rt_fp = manifest["runtime_fingerprints"]
    src_fp = manifest["source_fingerprints"]

    actual_rt_cal_sha = _sha256(member_bytes["runtime_calibration.json"])
    if rt_fp.get("runtime_calibration_sha256") != actual_rt_cal_sha:
        raise FormalBundleValidationError("runtime_calibration.json SHA-256 mismatch")

    actual_rt_reg_sha = _sha256(member_bytes["packaging_rule_registry_v1.json"])
    if rt_fp.get("runtime_registry_sha256") != actual_rt_reg_sha:
        raise FormalBundleValidationError("packaging_rule_registry_v1.json SHA-256 mismatch")

    actual_val_pkg_sha = _sha256(member_bytes["validated_rule_package.json"])
    if src_fp.get("validated_rule_package_sha256") != actual_val_pkg_sha:
        raise FormalBundleValidationError("validated_rule_package.json SHA-256 mismatch")

    actual_receipt_sha = _sha256(member_bytes["promotion_receipt.json"])
    if src_fp.get("promotion_receipt_sha256") != actual_receipt_sha:
        raise FormalBundleValidationError("promotion_receipt.json SHA-256 mismatch")

    # ── validated package ──
    if not isinstance(validated_pkg, dict):
        raise FormalBundleValidationError("validated_package must be a JSON object")
    validation_result = AgentCalibrationRulePackageValidator().validate(
        validated_pkg, require_validated=True
    )
    if not validation_result.is_valid:
        detail = "; ".join(f"{i.path}: {i.message}" for i in validation_result.issues)
        raise FormalBundleValidationError(f"validated package invalid: {detail}")

    if validated_pkg.get("status") != "validated":
        raise FormalBundleValidationError("validated_package status must be 'validated'")
    if validated_pkg.get("package_id") != manifest["package_id"]:
        raise FormalBundleValidationError("validated_package package_id != manifest package_id")
    if validated_pkg.get("calibration_version") != manifest["calibration_version"]:
        raise FormalBundleValidationError("validated_package calibration_version != manifest")

    val_block = validated_pkg.get("validation")
    if not isinstance(val_block, dict):
        raise FormalBundleValidationError("validated_package missing validation block")
    if val_block.get("engine_version") != manifest["engine_version"]:
        raise FormalBundleValidationError("validated_package engine_version != manifest")
    if val_block.get("baseline_calibration_version") != manifest["baseline_calibration_version"]:
        raise FormalBundleValidationError("validated_package baseline_calibration_version != manifest")

    # ── promotion receipt ──
    if not isinstance(receipt, dict):
        raise FormalBundleValidationError("promotion_receipt must be a JSON object")
    if receipt.get("candidate_package_id") != manifest["package_id"]:
        raise FormalBundleValidationError("receipt candidate_package_id != manifest package_id")
    if receipt.get("validated_package_sha256") != actual_val_pkg_sha:
        raise FormalBundleValidationError("receipt validated_package_sha256 != actual validated package SHA")
    if receipt.get("baseline_calibration_version") != manifest["baseline_calibration_version"]:
        raise FormalBundleValidationError("receipt baseline_calibration_version != manifest")
    if receipt.get("validation_counts") != val_block:
        raise FormalBundleValidationError("receipt validation_counts != validated_package validation block")

    coverage = receipt.get("rule_coverage")
    if not isinstance(coverage, dict):
        raise FormalBundleValidationError("receipt missing rule_coverage")
    if coverage.get("uncovered_rule_ids") != []:
        raise FormalBundleValidationError("receipt uncovered_rule_ids must be empty")

    # ── runtime calibration ──
    if not isinstance(runtime_cal, list) or not runtime_cal:
        raise FormalBundleValidationError("runtime_calibration must be a non-empty list")
    if not all(isinstance(item, dict) for item in runtime_cal):
        raise FormalBundleValidationError("runtime_calibration members must all be objects")

    # ── runtime registry ──
    if not isinstance(runtime_reg, dict):
        raise FormalBundleValidationError("registry must be a JSON object")
    for key in ("aggregate_rules", "sample_rules"):
        val = runtime_reg.get(key)
        if not isinstance(val, list):
            raise FormalBundleValidationError(f"registry.{key} must be a list")
        if not all(isinstance(item, dict) for item in val):
            raise FormalBundleValidationError(f"registry.{key} members must all be objects")
    reg_version = runtime_reg.get("version")
    if reg_version != manifest["calibration_version"]:
        raise FormalBundleValidationError(
            f"registry.version {reg_version!r} != manifest calibration_version {manifest['calibration_version']!r}"
        )

    # ── runtime_summary 与真实数据交叉验证 ──
    summary = manifest["runtime_summary"]
    actual_sample_count = len(runtime_cal)
    if summary.get("sample_count") != actual_sample_count:
        raise FormalBundleValidationError(
            f"runtime_summary.sample_count {summary.get('sample_count')} != actual {actual_sample_count}"
        )
    actual_aggregate_count = len(runtime_reg.get("aggregate_rules", []))
    if summary.get("aggregate_rule_count") != actual_aggregate_count:
        raise FormalBundleValidationError(
            f"runtime_summary.aggregate_rule_count {summary.get('aggregate_rule_count')} != actual {actual_aggregate_count}"
        )
    actual_sample_rule_count = len(runtime_reg.get("sample_rules", []))
    if summary.get("sample_rule_count") != actual_sample_rule_count:
        raise FormalBundleValidationError(
            f"runtime_summary.sample_rule_count {summary.get('sample_rule_count')} != actual {actual_sample_rule_count}"
        )
    # validated_rule_ids: 必须等于 validated package 中 enabled=true 的 rule_id 列表
    actual_validated_ids = sorted(
        str(rule.get("rule_id"))
        for rule in validated_pkg.get("rules", [])
        if isinstance(rule, dict) and rule.get("enabled") is True
    )
    declared_ids = summary.get("validated_rule_ids", [])
    if sorted(declared_ids) != actual_validated_ids:
        raise FormalBundleValidationError(
            f"runtime_summary.validated_rule_ids {declared_ids} != actual enabled rules {actual_validated_ids}"
        )

    return ValidatedFormalBundle(
        manifest=manifest,
        runtime_calibration=runtime_cal,
        runtime_registry=runtime_reg,
        validated_package=validated_pkg,
        promotion_receipt=receipt,
        member_bytes=member_bytes,
        zip_sha256=zip_sha,
    )


def is_formal_bundle_zip(zip_path: str | Path) -> bool:
    """Quick check: does this ZIP contain formal_package_manifest.json at ROOT level?"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            root_members = {
                name for name in (info.filename for info in archive.infolist())
                if _is_root_level_member(name)
            }
            return "formal_package_manifest.json" in root_members
    except (zipfile.BadZipFile, OSError):
        return False
