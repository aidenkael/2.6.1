from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService

SCHEMA_VERSION = "agent-calibration-rule-package-v1"

_TOP_KEYS = {
    "schema_version", "package_id", "calibration_version", "created_at", "generator",
    "source_export_batch_ids", "base_engine_version", "base_calibration_version",
    "status", "rules", "validation",
}
_REQUIRED_TOP = _TOP_KEYS - {"base_calibration_version"}

_RULE_KEYS = {"rule_id", "enabled", "priority", "description", "match", "guard", "action", "evidence"}
_REQUIRED_RULE = {"rule_id", "enabled", "priority", "match", "action", "evidence"}

_MATCH_KEYS = {
    "any_terms", "materials", "rigidity", "foldability", "compressibility",
    "forbid_hard_structure", "requires_shape_retention",
}
_MATCH_LIST_KEYS = {"any_terms", "materials", "rigidity", "foldability", "compressibility"}
_GUARD_KEYS = {"any_hard_structure_or_shape_retention", "foldability_not"}
_EVIDENCE_KEYS = {"source_record_ids", "sample_count", "rationale"}

_VALIDATION_KEYS = {
    "validator", "replay_id", "engine_version", "baseline_calibration_version",
    "total_records", "matched", "improved", "unchanged", "degraded", "conflicts",
}
_REQUIRED_VALIDATION = _VALIDATION_KEYS - {"baseline_calibration_version"}

_ACTION_ALLOWED = {
    "smallest_axis_scale": {"type", "normal", "conservative", "min_cm"},
    "smallest_axis_add": {"type", "normal_cm", "conservative_cm"},
    "volume_ratio": {"type", "normal", "conservative"},
    "reference_scaled_template": {
        "type", "reference_product_size_cm", "normal_package_size_cm",
        "conservative_package_size_cm", "scale_min", "scale_max",
    },
}
_ACTION_REQUIRED = {
    "smallest_axis_scale": {"type", "normal", "conservative"},
    "smallest_axis_add": {"type", "normal_cm", "conservative_cm"},
    "volume_ratio": {"type", "normal", "conservative"},
    "reference_scaled_template": {
        "type", "reference_product_size_cm", "normal_package_size_cm",
        "conservative_package_size_cm",
    },
}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def raise_for_errors(self) -> None:
        if not self.issues:
            return
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        raise ValueError(f"Agent calibration rule package validation failed: {detail}")


class AgentCalibrationRulePackageValidator:
    """Side-effect-free validator for Agent Calibration Rule Package V1.

    It validates contract structure and deterministic semantic safety only. It does
    not import/activate packages, run replay, choose promotion thresholds, or touch CAL77.
    """

    def __init__(self, *, expected_engine_version: str | None = None) -> None:
        self.expected_engine_version = (
            str(expected_engine_version).strip()
            if expected_engine_version is not None
            else PackagingEstimationService.ENGINE_VERSION
        )

    def validate(self, payload: Any, *, require_validated: bool = False) -> ValidationResult:
        issues: list[ValidationIssue] = []

        def add(code: str, path: str, message: str) -> None:
            issues.append(ValidationIssue(code, path, message))

        if not isinstance(payload, dict):
            add("root_type", "$", "root must be a JSON object")
            return ValidationResult(tuple(issues))

        self._exact_keys(payload, _TOP_KEYS, _REQUIRED_TOP, "$", add)
        self._string(payload.get("package_id"), "$.package_id", add, 128)
        self._string(payload.get("calibration_version"), "$.calibration_version", add, 128)
        self._string(payload.get("generator"), "$.generator", add, 128)
        if "base_calibration_version" in payload:
            self._string(payload.get("base_calibration_version"), "$.base_calibration_version", add, 128)

        if payload.get("schema_version") != SCHEMA_VERSION:
            add("schema_version", "$.schema_version", f"must equal {SCHEMA_VERSION!r}")

        self._utc_datetime(payload.get("created_at"), "$.created_at", add)
        self._string_list(payload.get("source_export_batch_ids"), "$.source_export_batch_ids", add, 128)

        engine = payload.get("base_engine_version")
        self._string(engine, "$.base_engine_version", add, 128)
        if isinstance(engine, str) and engine.strip() and self.expected_engine_version and engine != self.expected_engine_version:
            add("engine_version_mismatch", "$.base_engine_version", f"expected {self.expected_engine_version!r}")

        status = payload.get("status")
        if status not in {"candidate", "validated"}:
            add("status", "$.status", "must be 'candidate' or 'validated'")
        elif require_validated and status != "validated":
            add("validated_required", "$.status", "validated package required")

        rules = payload.get("rules")
        if not isinstance(rules, list) or not rules:
            add("rules", "$.rules", "must be a non-empty list")
        else:
            seen: set[str] = set()
            for index, rule in enumerate(rules):
                path = f"$.rules[{index}]"
                self._rule(rule, path, add)
                if isinstance(rule, dict):
                    rule_id = rule.get("rule_id")
                    if isinstance(rule_id, str) and rule_id.strip():
                        if rule_id in seen:
                            add("duplicate_rule_id", f"{path}.rule_id", f"duplicate rule_id {rule_id!r}")
                        seen.add(rule_id)
            self._same_priority_conflicts(rules, add)

        validation = payload.get("validation")
        if status == "candidate" and validation is not None:
            add("candidate_has_validation", "$.validation", "candidate packages must keep validation = null")
        elif status == "validated":
            if not isinstance(validation, dict):
                add("validated_missing_validation", "$.validation", "validated packages require software-side validation metadata")
            else:
                self._validation_block(validation, add)

        return ValidationResult(tuple(issues))

    def validate_file(self, path: str | Path, *, require_validated: bool = False) -> ValidationResult:
        source = Path(path)
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return ValidationResult((ValidationIssue("json_read_error", "$", f"cannot read JSON package: {exc}"),))
        return self.validate(payload, require_validated=require_validated)

    @staticmethod
    def _exact_keys(value: Any, allowed: set[str], required: set[str], path: str, add: Callable) -> None:
        if not isinstance(value, dict):
            add("object_type", path, "must be an object")
            return
        for key in sorted(set(value) - allowed):
            add("unknown_field", f"{path}.{key}", "field is not allowed by V1")
        for key in sorted(required - set(value)):
            add("missing_field", f"{path}.{key}", "required field is missing")

    @staticmethod
    def _string(value: Any, path: str, add: Callable, max_length: int) -> None:
        if not isinstance(value, str) or not value.strip():
            add("string", path, "must be a non-empty string")
        elif len(value) > max_length:
            add("string_length", path, f"must be <= {max_length} characters")

    @staticmethod
    def _utc_datetime(value: Any, path: str, add: Callable) -> None:
        if not isinstance(value, str) or not value.strip():
            add("datetime", path, "must be an ISO-8601 UTC timestamp")
            return
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            add("datetime", path, "must be an ISO-8601 UTC timestamp")
            return
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            add("datetime_timezone", path, "timestamp must be UTC")

    @classmethod
    def _string_list(cls, value: Any, path: str, add: Callable, max_length: int | None = None) -> None:
        if not isinstance(value, list) or not value:
            add("string_list", path, "must be a non-empty list of unique strings")
            return
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, str) or not item.strip():
                add("string_list_item", item_path, "must be a non-empty string")
                continue
            if max_length is not None and len(item) > max_length:
                add("string_length", item_path, f"must be <= {max_length} characters")
            if item in seen:
                add("duplicate_list_item", item_path, f"duplicate value {item!r}")
            seen.add(item)

    @staticmethod
    def _number(value: Any, path: str, add: Callable, *, positive: bool) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            add("number", path, "must be a finite number")
            return False
        number = float(value)
        if not math.isfinite(number):
            add("number_finite", path, "must be finite")
            return False
        if positive and number <= 0:
            add("number_positive", path, "must be > 0")
            return False
        if not positive and number < 0:
            add("number_nonnegative", path, "must be >= 0")
            return False
        return True

    def _rule(self, rule: Any, path: str, add: Callable) -> None:
        self._exact_keys(rule, _RULE_KEYS, _REQUIRED_RULE, path, add)
        if not isinstance(rule, dict):
            return
        self._string(rule.get("rule_id"), f"{path}.rule_id", add, 128)
        if not isinstance(rule.get("enabled"), bool):
            add("enabled", f"{path}.enabled", "must be boolean")
        priority = rule.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100000:
            add("priority", f"{path}.priority", "must be an integer between 0 and 100000")
        if "description" in rule and (not isinstance(rule.get("description"), str) or len(rule.get("description")) > 2000):
            add("description", f"{path}.description", "must be a string <= 2000 characters")
        self._match(rule.get("match"), f"{path}.match", add)
        if "guard" in rule:
            self._guard(rule.get("guard"), f"{path}.guard", add)
        self._action(rule.get("action"), f"{path}.action", add)
        self._evidence(rule.get("evidence"), f"{path}.evidence", add)

    def _match(self, match: Any, path: str, add: Callable) -> None:
        if not isinstance(match, dict):
            add("match", path, "must be a non-empty object")
            return
        self._exact_keys(match, _MATCH_KEYS, set(), path, add)
        if not match:
            add("empty_match", path, "match must contain at least one condition")
            return
        for key in _MATCH_LIST_KEYS:
            if key in match:
                self._string_list(match.get(key), f"{path}.{key}", add)
        if "forbid_hard_structure" in match and match.get("forbid_hard_structure") is not True:
            add("forbid_hard_structure", f"{path}.forbid_hard_structure", "V1 only allows the literal true value")
        if "requires_shape_retention" in match and not isinstance(match.get("requires_shape_retention"), bool):
            add("requires_shape_retention", f"{path}.requires_shape_retention", "must be boolean")

    def _guard(self, guard: Any, path: str, add: Callable) -> None:
        if not isinstance(guard, dict):
            add("guard", path, "must be a non-empty object")
            return
        self._exact_keys(guard, _GUARD_KEYS, set(), path, add)
        if not guard:
            add("empty_guard", path, "guard must contain at least one condition")
            return
        if "any_hard_structure_or_shape_retention" in guard and not isinstance(guard.get("any_hard_structure_or_shape_retention"), bool):
            add("guard_boolean", f"{path}.any_hard_structure_or_shape_retention", "must be boolean")
        if "foldability_not" in guard:
            self._string_list(guard.get("foldability_not"), f"{path}.foldability_not", add)

    def _action(self, action: Any, path: str, add: Callable) -> None:
        if not isinstance(action, dict):
            add("action", path, "must be an object")
            return
        kind = action.get("type")
        if kind not in _ACTION_ALLOWED:
            add("action_type", f"{path}.type", "unsupported action type")
            return
        self._exact_keys(action, _ACTION_ALLOWED[kind], _ACTION_REQUIRED[kind], path, add)

        if kind in {"smallest_axis_scale", "volume_ratio"}:
            normal_ok = self._number(action.get("normal"), f"{path}.normal", add, positive=True)
            conservative_ok = self._number(action.get("conservative"), f"{path}.conservative", add, positive=True)
            if kind == "smallest_axis_scale" and "min_cm" in action:
                self._number(action.get("min_cm"), f"{path}.min_cm", add, positive=True)
            if normal_ok and conservative_ok and float(action["conservative"]) < float(action["normal"]):
                add("conservative_below_normal", path, "conservative value must be >= normal value")
            return

        if kind == "smallest_axis_add":
            normal_ok = self._number(action.get("normal_cm"), f"{path}.normal_cm", add, positive=False)
            conservative_ok = self._number(action.get("conservative_cm"), f"{path}.conservative_cm", add, positive=False)
            if normal_ok and conservative_ok and float(action["conservative_cm"]) < float(action["normal_cm"]):
                add("conservative_below_normal", path, "conservative add must be >= normal add")
            return

        triples: dict[str, tuple[float, float, float] | None] = {}
        for key in ("reference_product_size_cm", "normal_package_size_cm", "conservative_package_size_cm"):
            triples[key] = self._triple(action.get(key), f"{path}.{key}", add)
        for key in ("scale_min", "scale_max"):
            if key in action:
                self._number(action.get(key), f"{path}.{key}", add, positive=True)
        if self._positive(action.get("scale_min")) and self._positive(action.get("scale_max")) and float(action["scale_max"]) < float(action["scale_min"]):
            add("scale_bounds", path, "scale_max must be >= scale_min")
        normal = triples["normal_package_size_cm"]
        conservative = triples["conservative_package_size_cm"]
        if normal and conservative and any(c < n for n, c in zip(normal, conservative, strict=True)):
            add("conservative_below_normal", path, "each conservative template dimension must be >= its normal dimension")

    @staticmethod
    def _positive(value: Any) -> bool:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0

    def _triple(self, value: Any, path: str, add: Callable) -> tuple[float, float, float] | None:
        if not isinstance(value, list) or len(value) != 3:
            add("dimension_triple", path, "must contain exactly three positive numbers")
            return None
        parsed: list[float] = []
        valid = True
        for index, item in enumerate(value):
            if self._number(item, f"{path}[{index}]", add, positive=True):
                parsed.append(float(item))
            else:
                valid = False
        return tuple(parsed) if valid else None

    def _evidence(self, evidence: Any, path: str, add: Callable) -> None:
        if not isinstance(evidence, dict):
            add("evidence", path, "must be an object")
            return
        self._exact_keys(evidence, _EVIDENCE_KEYS, {"source_record_ids", "sample_count"}, path, add)
        source_ids = evidence.get("source_record_ids")
        self._string_list(source_ids, f"{path}.source_record_ids", add, 128)
        sample_count = evidence.get("sample_count")
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1:
            add("sample_count", f"{path}.sample_count", "must be an integer >= 1")
        elif isinstance(source_ids, list):
            unique_valid_ids = {item for item in source_ids if isinstance(item, str) and item.strip()}
            if sample_count < len(unique_valid_ids):
                add("sample_count_mismatch", f"{path}.sample_count", "must be >= unique source_record_ids count")
        if "rationale" in evidence and (not isinstance(evidence.get("rationale"), str) or len(evidence.get("rationale")) > 2000):
            add("rationale", f"{path}.rationale", "must be a string <= 2000 characters")

    def _validation_block(self, validation: dict[str, Any], add: Callable) -> None:
        path = "$.validation"
        self._exact_keys(validation, _VALIDATION_KEYS, _REQUIRED_VALIDATION, path, add)
        for key in ("validator", "replay_id", "engine_version"):
            self._string(validation.get(key), f"{path}.{key}", add, 128)
        if "baseline_calibration_version" in validation:
            self._string(validation.get("baseline_calibration_version"), f"{path}.baseline_calibration_version", add, 128)
        engine = validation.get("engine_version")
        if isinstance(engine, str) and engine.strip() and self.expected_engine_version and engine != self.expected_engine_version:
            add("validation_engine_version_mismatch", f"{path}.engine_version", f"expected {self.expected_engine_version!r}")

        counts: dict[str, int] = {}
        for key in ("total_records", "matched", "improved", "unchanged", "degraded", "conflicts"):
            value = validation.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                add("validation_count", f"{path}.{key}", "must be an integer >= 0")
            else:
                counts[key] = value
        if {"total_records", "matched"} <= counts.keys() and counts["matched"] > counts["total_records"]:
            add("validation_counts", path, "matched cannot exceed total_records")
        if {"matched", "improved", "unchanged", "degraded"} <= counts.keys() and counts["improved"] + counts["unchanged"] + counts["degraded"] != counts["matched"]:
            add("validation_counts", path, "improved + unchanged + degraded must equal matched")

    def _same_priority_conflicts(self, rules: list[Any], add: Callable) -> None:
        typed = [rule for rule in rules if isinstance(rule, dict)]
        for index, left in enumerate(typed):
            priority = left.get("priority")
            if isinstance(priority, bool) or not isinstance(priority, int):
                continue
            for right in typed[index + 1:]:
                if right.get("priority") != priority:
                    continue
                if self._matches_overlap(left.get("match"), right.get("match")):
                    add(
                        "same_priority_overlap", "$.rules",
                        f"rules {left.get('rule_id')!r} and {right.get('rule_id')!r} share priority {priority} and overlap",
                    )

    @classmethod
    def _matches_overlap(cls, left: Any, right: Any) -> bool:
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        for key in ("rigidity", "foldability", "compressibility"):
            if isinstance(left.get(key), list) and isinstance(right.get(key), list) and set(map(str, left[key])).isdisjoint(set(map(str, right[key]))):
                return False
        if isinstance(left.get("requires_shape_retention"), bool) and isinstance(right.get("requires_shape_retention"), bool) and left["requires_shape_retention"] is not right["requires_shape_retention"]:
            return False
        if cls._term_lists_disjoint(left.get("any_terms"), right.get("any_terms")):
            return False
        if cls._term_lists_disjoint(left.get("materials"), right.get("materials")):
            return False
        return True

    @staticmethod
    def _term_lists_disjoint(left: Any, right: Any) -> bool:
        if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
            return False
        left_terms = [str(item).casefold() for item in left]
        right_terms = [str(item).casefold() for item in right]
        return not any(a in b or b in a for a in left_terms for b in right_terms)
