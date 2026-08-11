"""Candidate -> validated promotion for Agent Calibration Rule Package V1.

Promotion is software-owned and offline.  It never imports or activates a package.
The promoter re-runs Offline Replay V1 from the original inputs and compares the
fresh deterministic result with the reviewed replay artifact (ignoring only the
random replay_id).  This prevents an edited replay JSON from being used as the
basis for a validated package.

No numerical quality threshold is hard-coded in V1.  Every enabled candidate
rule must nevertheless have at least one evaluable record where that rule was
actually applied.  Degraded matched records require an explicit operator
acknowledgement via ``allow_degraded``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from profit_accounting_26.application.calibration_offline_replay import (
    REPLAY_VERSION,
    OfflineCalibrationReplay,
    load_json_and_hash,
)
from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)

PROMOTION_VERSION = "calibration-promotion-v1"
_JUDGED_STATUSES = {"improved", "unchanged", "degraded"}


class PromotionPrecheckError(ValueError):
    """Promotion cannot proceed because provenance, coverage or approval failed."""


@dataclass(frozen=True, slots=True)
class PromotionArtifacts:
    """Validated package plus software-generated promotion receipt."""

    validated_package: dict[str, Any]
    promotion_receipt: dict[str, Any]
    validated_package_bytes: bytes


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromotionPrecheckError(f"{field} must be a non-empty string")
    return value.strip()


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_replay_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Replay content that must be deterministic across repeated execution."""
    stable = copy.deepcopy(payload)
    stable.pop("replay_id", None)
    return stable


def _promotion_counts(replay: dict[str, Any]) -> tuple[dict[str, int], set[str]]:
    """Return validation counts over evaluable records where candidate truly applied.

    Replay summary counts intentionally have broader semantics: ``unchanged`` may
    include records where no candidate rule applied, and ``matched`` may include
    records without enough truth to score.  The Rule Package V1 validation block,
    however, requires improved + unchanged + degraded == matched.  Promotion
    therefore uses only records that are both candidate-matched and evaluable.
    """
    per_record = replay.get("per_record")
    if not isinstance(per_record, list):
        raise PromotionPrecheckError("reviewed replay per_record must be a list")

    matched_evaluable: list[dict[str, Any]] = []
    covered_rule_ids: set[str] = set()
    for item in per_record:
        if not isinstance(item, dict):
            raise PromotionPrecheckError("reviewed replay per_record entries must be objects")
        status = item.get("status")
        candidate_rule_ids = item.get("candidate_rule_ids")
        if status in _JUDGED_STATUSES and item.get("matched") is True:
            if not isinstance(candidate_rule_ids, list) or not candidate_rule_ids:
                raise PromotionPrecheckError(
                    "matched evaluable replay record must contain candidate_rule_ids"
                )
            matched_evaluable.append(item)
            covered_rule_ids.update(str(rule_id) for rule_id in candidate_rule_ids)

    counts = {
        "matched": len(matched_evaluable),
        "improved": sum(1 for item in matched_evaluable if item.get("status") == "improved"),
        "unchanged": sum(1 for item in matched_evaluable if item.get("status") == "unchanged"),
        "degraded": sum(1 for item in matched_evaluable if item.get("status") == "degraded"),
    }
    return counts, covered_rule_ids


class CalibrationRulePackagePromoter:
    """Promote one immutable candidate package after reviewed replay verification."""

    def promote(
        self,
        *,
        candidate_package: str | Path,
        reviewed_replay: str | Path,
        feedback_manifest: str | Path,
        baseline_calibration: str | Path,
        baseline_registry: str | Path,
        baseline_calibration_version: str,
        approved_by: str,
        acknowledge_reviewed_replay: bool,
        allow_degraded: bool = False,
        approval_note: str | None = None,
    ) -> PromotionArtifacts:
        if not acknowledge_reviewed_replay:
            raise PromotionPrecheckError(
                "explicit acknowledge_reviewed_replay=True is required for promotion"
            )
        approver = _nonempty_string(approved_by, "approved_by")
        baseline_version = _nonempty_string(
            baseline_calibration_version, "baseline_calibration_version"
        )
        if approval_note is not None and not isinstance(approval_note, str):
            raise PromotionPrecheckError("approval_note must be a string or null")

        candidate, candidate_sha256 = load_json_and_hash(candidate_package)
        if not isinstance(candidate, dict):
            raise PromotionPrecheckError("candidate package must be a JSON object")

        candidate_validator = AgentCalibrationRulePackageValidator()
        candidate_result = candidate_validator.validate(candidate)
        if not candidate_result.is_valid or candidate.get("status") != "candidate":
            details = "; ".join(
                f"{issue.path}: {issue.message}" for issue in candidate_result.issues
            )
            suffix = f": {details}" if details else ""
            raise PromotionPrecheckError(f"valid candidate package required{suffix}")

        reviewed, reviewed_replay_sha256 = load_json_and_hash(reviewed_replay)
        if not isinstance(reviewed, dict):
            raise PromotionPrecheckError("reviewed replay must be a JSON object")
        if reviewed.get("replay_version") != REPLAY_VERSION:
            raise PromotionPrecheckError(
                f"reviewed replay_version must equal {REPLAY_VERSION!r}"
            )
        reviewed_replay_id = _nonempty_string(reviewed.get("replay_id"), "replay_id")

        # Re-run the exact replay path.  All software formulas stay inside the
        # existing OfflineCalibrationReplay / PackagingEstimationService chain.
        fresh = OfflineCalibrationReplay().run(
            feedback_manifest=feedback_manifest,
            candidate_package=candidate_package,
            baseline_calibration=baseline_calibration,
            baseline_registry=baseline_registry,
            baseline_calibration_version=baseline_version,
        )
        if _stable_replay_view(reviewed) != _stable_replay_view(fresh):
            raise PromotionPrecheckError(
                "reviewed replay does not match a fresh replay of the supplied inputs"
            )

        fingerprints = reviewed.get("input_fingerprints")
        if not isinstance(fingerprints, dict):
            raise PromotionPrecheckError("reviewed replay input_fingerprints missing")
        if fingerprints.get("candidate_package_sha256") != candidate_sha256:
            raise PromotionPrecheckError(
                "reviewed replay candidate fingerprint does not match candidate bytes"
            )

        summary = reviewed.get("summary")
        if not isinstance(summary, dict):
            raise PromotionPrecheckError("reviewed replay summary missing")
        if summary.get("conflicts") != 0:
            raise PromotionPrecheckError("replay with conflicts cannot be promoted")

        counts, covered_rule_ids = _promotion_counts(reviewed)
        if counts["matched"] == 0:
            raise PromotionPrecheckError(
                "candidate has no evaluable record where a candidate rule was actually applied"
            )

        enabled_rule_ids = [
            str(rule.get("rule_id"))
            for rule in candidate.get("rules", [])
            if isinstance(rule, dict) and rule.get("enabled") is True
        ]
        if not enabled_rule_ids:
            raise PromotionPrecheckError("candidate contains no enabled rules")
        uncovered_rule_ids = [
            rule_id for rule_id in enabled_rule_ids if rule_id not in covered_rule_ids
        ]
        if uncovered_rule_ids:
            raise PromotionPrecheckError(
                "every enabled rule requires evaluable applied coverage; uncovered rule_ids="
                + ", ".join(uncovered_rule_ids)
            )

        if counts["degraded"] > 0 and not allow_degraded:
            raise PromotionPrecheckError(
                "degraded matched records are present; explicit allow_degraded=True is required"
            )

        validated = copy.deepcopy(candidate)
        validated["status"] = "validated"
        validated["validation"] = {
            "validator": PROMOTION_VERSION,
            "replay_id": reviewed_replay_id,
            "engine_version": reviewed.get("engine_version"),
            "baseline_calibration_version": reviewed.get("baseline_calibration_version"),
            "total_records": int(summary.get("total_records", 0)),
            "matched": counts["matched"],
            "improved": counts["improved"],
            "unchanged": counts["unchanged"],
            "degraded": counts["degraded"],
            "conflicts": 0,
        }

        validated_result = AgentCalibrationRulePackageValidator().validate(
            validated, require_validated=True
        )
        if not validated_result.is_valid:
            detail = "; ".join(
                f"{issue.path}: {issue.message}" for issue in validated_result.issues
            )
            raise PromotionPrecheckError(
                f"software-generated validated package failed V1 validator: {detail}"
            )

        validated_bytes = _canonical_json_bytes(validated)
        validated_sha256 = _sha256_bytes(validated_bytes)

        warnings: list[str] = []
        if counts["degraded"] > 0:
            warnings.append("degraded_matched_records_explicitly_accepted")
        if int(summary.get("unmatched", 0) or 0) > 0:
            warnings.append("replay_contains_unmatched_records")
        if int(summary.get("insufficient_truth", 0) or 0) > 0:
            warnings.append("replay_contains_insufficient_truth_records")

        promoted_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        receipt = {
            "promotion_version": PROMOTION_VERSION,
            "promoted_at": promoted_at,
            "approved_by": approver,
            "approval_note": approval_note,
            "allow_degraded": bool(allow_degraded),
            "candidate_package_id": str(candidate.get("package_id") or ""),
            "reviewed_replay_id": reviewed_replay_id,
            "candidate_package_sha256": candidate_sha256,
            "reviewed_replay_sha256": reviewed_replay_sha256,
            "validated_package_sha256": validated_sha256,
            "input_fingerprints": copy.deepcopy(fingerprints),
            "baseline_calibration_version": baseline_version,
            "validation_counts": copy.deepcopy(validated["validation"]),
            "rule_coverage": {
                "enabled_rule_ids": enabled_rule_ids,
                "covered_rule_ids": [
                    rule_id for rule_id in enabled_rule_ids if rule_id in covered_rule_ids
                ],
                "uncovered_rule_ids": [],
            },
            "warnings": warnings,
        }
        return PromotionArtifacts(
            validated_package=validated,
            promotion_receipt=receipt,
            validated_package_bytes=validated_bytes,
        )


def promote_candidate(
    *,
    candidate_package: str | Path,
    reviewed_replay: str | Path,
    feedback_manifest: str | Path,
    baseline_calibration: str | Path,
    baseline_registry: str | Path,
    baseline_calibration_version: str,
    approved_by: str,
    acknowledge_reviewed_replay: bool,
    allow_degraded: bool = False,
    approval_note: str | None = None,
) -> PromotionArtifacts:
    return CalibrationRulePackagePromoter().promote(
        candidate_package=candidate_package,
        reviewed_replay=reviewed_replay,
        feedback_manifest=feedback_manifest,
        baseline_calibration=baseline_calibration,
        baseline_registry=baseline_registry,
        baseline_calibration_version=baseline_calibration_version,
        approved_by=approved_by,
        acknowledge_reviewed_replay=acknowledge_reviewed_replay,
        allow_degraded=allow_degraded,
        approval_note=approval_note,
    )
