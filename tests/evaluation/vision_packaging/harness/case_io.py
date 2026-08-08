"""Evaluation case format: loading, validation and discovery.

Real evaluation cases live OUTSIDE the repository (never committed):

    <data_dir>/cases/<case_id>/case.json
    <data_dir>/cases/<case_id>/ai_raw_response.json
    <data_dir>/cases/<case_id>/images/            (optional, local only)

``data_dir`` resolution order:
    1. explicit ``--data-dir`` argument
    2. environment variable ``PROFIT_ACCOUNTING_EVAL_DATA_DIR``
    3. default ``E:/Profit-Accounting-2.6.1-evaluation-data``

Synthetic cases ship inside the repository under ``synthetic/`` next to this
package. They are mechanism regression fixtures only and must never be mixed
into real accuracy statistics.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "vision-packaging-eval-case-v1"
ENV_DATA_DIR = "PROFIT_ACCOUNTING_EVAL_DATA_DIR"
DEFAULT_DATA_DIR = Path("E:/Profit-Accounting-2.6.1-evaluation-data")

IMAGE_ROLES = ("main", "dimension", "weight", "packaging", "other", "unknown")

# V2-compatible optional ground-truth sections (all fields may stay null).
# ``estimated_package`` grades the future single primary packaging result;
# the current engine's normal/conservative pair is legacy output only.
STRUCTURE_FEEDBACK_KEYS = (
    "rigidity", "shape_retention", "foldability", "compressibility",
    "foldable_parts", "coilable_parts", "detachable_parts", "rigid_parts",
    "axis_behavior",
)
ACTUAL_FEEDBACK_KEYS = (
    "actual_first_mile_fee_rmb", "actual_chargeable_weight_kg", "actual_forwarder",
    "actual_package_dimensions", "actual_package_weight", "actual_packaging_method",
)

CASE_FILE = "case.json"
RAW_RESPONSE_FILE = "ai_raw_response.json"

SYNTHETIC_DIR = Path(__file__).resolve().parents[1] / "synthetic"


class CaseFormatError(ValueError):
    """Raised when a case directory cannot be loaded as an evaluation case."""


@dataclass
class EvalCase:
    case_id: str
    path: Path
    metadata: dict[str, Any]
    raw_response: dict[str, Any]
    origin: str = "real"  # "real" | "synthetic"

    @property
    def ground_truth(self) -> dict[str, Any]:
        value = self.metadata.get("ground_truth")
        return value if isinstance(value, dict) else {}

    @property
    def image_roles(self) -> list[dict[str, Any]]:
        images = self.metadata.get("images")
        return [item for item in images if isinstance(item, dict)] if isinstance(images, list) else []


def resolve_data_dir(explicit: str | Path | None = None) -> Path | None:
    """Resolve the out-of-repo evaluation data directory, if any."""
    if explicit:
        return Path(str(explicit)).expanduser()
    env_value = os.environ.get(ENV_DATA_DIR, "").strip()
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_DATA_DIR if DEFAULT_DATA_DIR.is_dir() else None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CaseFormatError(f"无法读取 {path.name}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CaseFormatError(f"{path.name} 不是有效 JSON: {exc}") from exc


def _is_number_pair(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
        and float(value[0]) <= float(value[1])
    )


def validate_case_metadata(metadata: dict[str, Any]) -> list[str]:
    """Return human-readable issues. Empty list means the case is usable.

    The schema is intentionally permissive: every ground-truth field may be
    ``unknown`` or omitted so annotators are never forced to invent precise
    answers.
    """
    issues: list[str] = []
    if not isinstance(metadata, dict):
        return ["case.json 根节点必须是 JSON 对象"]
    if not str(metadata.get("case_id") or "").strip():
        issues.append("缺少 case_id")
    images = metadata.get("images")
    if images is not None:
        if not isinstance(images, list):
            issues.append("images 必须是列表")
        else:
            for index, item in enumerate(images):
                if not isinstance(item, dict):
                    issues.append(f"images[{index}] 必须是对象")
                    continue
                role = str(item.get("image_role") or "unknown")
                if role not in IMAGE_ROLES:
                    issues.append(f"images[{index}].image_role 非法: {role}（允许: {', '.join(IMAGE_ROLES)}）")
    truth = metadata.get("ground_truth")
    if truth is not None:
        if not isinstance(truth, dict):
            issues.append("ground_truth 必须是对象")
        else:
            issues.extend(_validate_ground_truth(truth))
    return issues


def _validate_ground_truth(truth: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in ("expected_product_summary", "expected_material", "expected_structure", "notes"):
        value = truth.get(key)
        if value is not None and not isinstance(value, str):
            issues.append(f"ground_truth.{key} 必须是字符串或 null")
    for key in ("bare_dimensions", "bare_weight"):
        spec = truth.get(key)
        if spec is None:
            continue
        if not isinstance(spec, dict):
            issues.append(f"ground_truth.{key} 必须是对象")
            continue
        if spec.get("unknown") not in (None, True, False):
            issues.append(f"ground_truth.{key}.unknown 必须是布尔值")
        acceptable = spec.get("acceptable_range")
        if key == "bare_dimensions" and acceptable is not None:
            if not isinstance(acceptable, dict):
                issues.append("ground_truth.bare_dimensions.acceptable_range 必须是对象")
            else:
                for axis in ("length_cm", "width_cm", "height_cm"):
                    pair = acceptable.get(axis)
                    if pair is not None and not _is_number_pair(pair):
                        issues.append(f"ground_truth.bare_dimensions.acceptable_range.{axis} 必须是 [min, max] 数字区间")
        if key == "bare_weight" and acceptable is not None and not _is_number_pair(acceptable):
            issues.append("ground_truth.bare_weight.acceptable_range 必须是 [min, max] 数字区间")
    for key in ("normal_packaging", "conservative_packaging"):
        spec = truth.get(key)
        if spec is None:
            continue
        if not isinstance(spec, dict):
            issues.append(f"ground_truth.{key} 必须是对象")
            continue
        for axis in ("length_range", "width_range", "height_range", "weight_range"):
            pair = spec.get(axis)
            if pair is not None and not _is_number_pair(pair):
                issues.append(f"ground_truth.{key}.{axis} 必须是 [min, max] 数字区间")
        methods = spec.get("acceptable_methods")
        if methods is not None:
            if not isinstance(methods, list) or not all(isinstance(item, str) for item in methods):
                issues.append(f"ground_truth.{key}.acceptable_methods 必须是字符串列表")
    estimated = truth.get("estimated_package")
    if estimated is not None:
        if not isinstance(estimated, dict):
            issues.append("ground_truth.estimated_package 必须是对象")
        else:
            nested = _validate_ground_truth({"normal_packaging": estimated})
            issues.extend(item.replace("normal_packaging", "estimated_package") for item in nested)
    structure = truth.get("structure_feedback")
    if structure is not None:
        if not isinstance(structure, dict):
            issues.append("ground_truth.structure_feedback 必须是对象")
        else:
            for item_key in structure:
                if item_key not in STRUCTURE_FEEDBACK_KEYS:
                    issues.append(f"ground_truth.structure_feedback.{item_key} 非法字段（允许: {', '.join(STRUCTURE_FEEDBACK_KEYS)}）")
            for parts_key in ("foldable_parts", "coilable_parts", "detachable_parts", "rigid_parts"):
                parts = structure.get(parts_key)
                if parts is not None and (not isinstance(parts, list) or not all(isinstance(item, str) for item in parts)):
                    issues.append(f"ground_truth.structure_feedback.{parts_key} 必须是字符串列表")
    actual = truth.get("actual_feedback")
    if actual is not None:
        if not isinstance(actual, dict):
            issues.append("ground_truth.actual_feedback 必须是对象")
        else:
            for item_key in actual:
                if item_key not in ACTUAL_FEEDBACK_KEYS:
                    issues.append(f"ground_truth.actual_feedback.{item_key} 非法字段（允许: {', '.join(ACTUAL_FEEDBACK_KEYS)}）")
            for number_key in ("actual_first_mile_fee_rmb", "actual_chargeable_weight_kg", "actual_package_weight"):
                number = actual.get(number_key)
                if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float))):
                    issues.append(f"ground_truth.actual_feedback.{number_key} 必须是数字或 null")
    return issues


def load_case(case_dir: str | Path, *, origin: str = "real") -> EvalCase:
    case_dir = Path(case_dir)
    case_path = case_dir / CASE_FILE
    raw_path = case_dir / RAW_RESPONSE_FILE
    if not case_path.is_file():
        raise CaseFormatError(f"缺少 {CASE_FILE}: {case_dir}")
    if not raw_path.is_file():
        raise CaseFormatError(f"缺少 {RAW_RESPONSE_FILE}: {case_dir}")
    metadata = _read_json(case_path)
    if not isinstance(metadata, dict):
        raise CaseFormatError("case.json 根节点必须是 JSON 对象")
    raw_response = _read_json(raw_path)
    if not isinstance(raw_response, dict):
        raise CaseFormatError("ai_raw_response.json 根节点必须是 JSON 对象（完整的 provider 响应）")
    case_id = str(metadata.get("case_id") or case_dir.name)
    issues = validate_case_metadata(metadata)
    if issues:
        raise CaseFormatError(f"案例 {case_id} 格式问题: " + "; ".join(issues))
    return EvalCase(case_id=case_id, path=case_dir, metadata=metadata, raw_response=raw_response, origin=origin)


def discover_real_cases(data_dir: str | Path | None) -> list[EvalCase]:
    """Discover real cases under ``<data_dir>/cases`` (sorted by case id)."""
    if not data_dir:
        return []
    cases_root = Path(data_dir) / "cases"
    if not cases_root.is_dir():
        return []
    cases: list[EvalCase] = []
    for child in sorted(cases_root.iterdir()):
        if not child.is_dir() or not (child / CASE_FILE).is_file():
            continue
        cases.append(load_case(child, origin="real"))
    return cases


def discover_synthetic_cases() -> list[EvalCase]:
    cases: list[EvalCase] = []
    if not SYNTHETIC_DIR.is_dir():
        return cases
    for child in sorted(SYNTHETIC_DIR.iterdir()):
        if not child.is_dir() or not (child / CASE_FILE).is_file():
            continue
        cases.append(load_case(child, origin="synthetic"))
    return cases
