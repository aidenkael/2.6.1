"""Offline Replay V1：同一批历史事实在同一 PackagingEstimationService 上运行 baseline 与 candidate。

输入（全部显式路径，V1 不操作数据库 / Settings / active calibration）：
- Calibration Feedback Export V2 ``manifest.json``（只读 ``records[].machine_facts``）；
- Agent Calibration Rule Package V1 candidate JSON；
- baseline calibration JSON；
- baseline ``packaging_rule_registry_v1.json``；
- 输出 ``replay_result.json`` 路径由 CLI 侧提供。

核心原则：
- 禁止复制软件包装公式：baseline 与 candidate 都调用现有
  ``PackagingEstimationService.estimate()``；
- candidate 只临时叠加到 registry 的 ``aggregate_rules``（保留原有 sample_rules），
  不调用 activate()、不写 CalibrationManager / calibration_packages / builtin / CAL77 / 数据库；
- 只使用 ``actual_package_dimensions`` / ``actual_package_weight_g`` 作为 truth，
  费用与计费重不参与包装评分；
- 不制定 promotion threshold，只用极小浮点 epsilon 区分 improved / unchanged / degraded。

候选规则有效性按 PackagingProposal 返回的 ``applied_profile_ids`` 与 candidate rule_id
的交集判断（matched / unmatched），不只看文本条件是否可能匹配。
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from profit_accounting_26.application.calibration_rule_package_validator import (
    AgentCalibrationRulePackageValidator,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario

REPLAY_VERSION = "offline-replay-v1"
_SCORE_EPSILON = 1e-9
_SCENARIO_SUMMARY_FIELDS = (
    "packaging_state",
    "packaging_method",
    "length_cm",
    "width_cm",
    "height_cm",
    "weight_g",
    "confidence",
    "needs_review",
)


class ReplayPrecheckError(ValueError):
    """candidate 预检失败：schema / status / engine / 包内冲突不通过，立即停止。"""


@dataclass(frozen=True)
class ReplayConflict:
    """candidate 与 baseline registry 的确定性冲突。"""

    code: str
    candidate_rule_id: str | None
    baseline_rule_id: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "candidate_rule_id": self.candidate_rule_id,
            "baseline_rule_id": self.baseline_rule_id,
            "message": self.message,
        }


class ReplayConflictError(ValueError):
    """候选规则与 baseline aggregate 规则冲突：记录 conflict 并停止正式 replay。"""

    def __init__(self, conflicts: list[ReplayConflict]) -> None:
        self.conflicts = list(conflicts)
        detail = "; ".join(conflict.message for conflict in self.conflicts)
        super().__init__(f"offline replay stopped by rule conflicts: {detail}")


# ---------------------------------------------------------------------------
# 输入读取
# ---------------------------------------------------------------------------


def load_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON input {source}: {exc}") from exc


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sha256_of_file(path: str | Path) -> str:
    """计算文件的 SHA-256，基于实际 bytes，不依赖重新序列化。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json_and_hash(path: str | Path) -> tuple[Any, str]:
    """读取 JSON 并同时计算文件 SHA-256（基于原始 bytes）。"""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read JSON input {source}: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        return json.loads(raw.decode("utf-8")), digest
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON input {source}: {exc}") from exc


# ---------------------------------------------------------------------------
# 历史输入重建（只读 machine_facts，不使用 current_estimate / 利润 / 售价 / 快照）
# ---------------------------------------------------------------------------


def rebuild_observation(ai_initial: dict[str, Any]) -> AIObservation | None:
    """从 machine_facts.ai_initial 重建 AIObservation。

    observation 白名单字段回到 AIObservation 顶层；evidence 的 field_evidence /
    confirmed_facts / dimension_semantic_issue / shipment 回到 raw_payload 对应结构。
    """
    observation_data = _as_dict(ai_initial.get("observation"))
    if not observation_data:
        return None
    payload = dict(observation_data)
    raw_payload: dict[str, Any] = {}
    evidence = _as_dict(ai_initial.get("evidence"))
    for key in ("field_evidence", "confirmed_facts"):
        block = evidence.get(key)
        if isinstance(block, dict):
            raw_payload[key] = block
    issue = evidence.get("dimension_semantic_issue")
    if isinstance(issue, str) and issue.strip():
        raw_payload["dimension_semantic_issue"] = issue
    shipment = evidence.get("shipment")
    if isinstance(shipment, dict):
        raw_payload["shipment"] = shipment
    payload["raw_payload"] = raw_payload
    return AIObservation.from_dict(payload)


def rebuild_external_proposal(ai_initial: dict[str, Any]) -> PackagingProposal | None:
    """从 machine_facts.ai_initial.packaging_proposal 重建 external PackagingProposal。

    manifest 只保存 normal/conservative 白名单字段，缺少 ``label``，这里按引擎惯例
    补“正常档/保守档”标签；historical applied_profile_ids 不在 manifest 中，置空。
    """
    proposal = _as_dict(ai_initial.get("packaging_proposal"))
    normal = proposal.get("normal")
    conservative = proposal.get("conservative")
    if not isinstance(normal, dict) or not isinstance(conservative, dict):
        return None
    try:
        return PackagingProposal(
            normal=PackagingScenario.from_dict({"label": "正常档", **normal}),
            conservative=PackagingScenario.from_dict({"label": "保守档", **conservative}),
            engine_version=str(proposal.get("engine_version") or PackagingEstimationService.ENGINE_VERSION),
            calibration_version=str(proposal.get("calibration_version") or ""),
            applied_profile_ids=[],
        )
    except (KeyError, TypeError, ValueError):
        return None


def extract_truth(user_feedback: Any) -> dict[str, Any]:
    """只提取真正包装事实：实际包装尺寸与实际包装重量。

    费用 / 计费重即使存在也不进入 truth（费用不能反推包装）。
    """
    feedback = _as_dict(user_feedback)
    actual = _as_dict(feedback.get("actual_logistics"))
    dimensions = actual.get("actual_package_dimensions")
    weight = actual.get("actual_package_weight_g")
    return {
        "dimensions": dimensions if isinstance(dimensions, dict) else None,
        "weight_g": weight,
    }


# ---------------------------------------------------------------------------
# candidate 预检与临时 registry
# ---------------------------------------------------------------------------


def validate_candidate(package: dict[str, Any]) -> None:
    """调用现有 AgentCalibrationRulePackageValidator；不通过立即抛 ReplayPrecheckError。"""
    result = AgentCalibrationRulePackageValidator().validate(package)
    if not result.is_valid:
        detail = "; ".join(f"{issue.path}: {issue.message}" for issue in result.issues)
        raise ReplayPrecheckError(f"Agent calibration rule package validation failed: {detail}")
    if package.get("status") != "candidate":
        raise ReplayPrecheckError(
            f"replay requires status='candidate', got {package.get('status')!r}; "
            "replay never auto-promotes a package to validated"
        )


def check_candidate_conflicts(
    package: dict[str, Any],
    baseline_registry: dict[str, Any],
) -> list[ReplayConflict]:
    """candidate 叠加 baseline aggregate_rules 前检查确定性冲突。

    复用 validator 的 ``_matches_overlap``，不另造一套判断算法：
    1. candidate rule_id 不得与现有 aggregate rule_id 重复；
    2. 同 priority 且 match 范围重叠 → conflict。
    """
    conflicts: list[ReplayConflict] = []
    existing = [rule for rule in baseline_registry.get("aggregate_rules", []) if isinstance(rule, dict)]
    existing_by_id = {str(rule.get("rule_id")): rule for rule in existing if rule.get("rule_id")}
    overlap = AgentCalibrationRulePackageValidator._matches_overlap
    for rule in package.get("rules", []):
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("rule_id") or "")
        if rule_id in existing_by_id:
            conflicts.append(
                ReplayConflict(
                    code="duplicate_rule_id",
                    candidate_rule_id=rule_id,
                    baseline_rule_id=rule_id,
                    message=f"candidate rule_id {rule_id!r} duplicates existing aggregate rule_id",
                )
            )
            continue
        priority = rule.get("priority")
        candidate_match = rule.get("match")
        if not isinstance(priority, int) or not isinstance(candidate_match, dict):
            continue
        for baseline_rule in existing:
            if baseline_rule.get("priority") != priority:
                continue
            baseline_match = baseline_rule.get("match")
            if isinstance(baseline_match, dict) and overlap(candidate_match, baseline_match):
                conflicts.append(
                    ReplayConflict(
                        code="same_priority_overlap",
                        candidate_rule_id=rule_id,
                        baseline_rule_id=str(baseline_rule.get("rule_id") or ""),
                        message=(
                            f"candidate rule {rule_id!r} shares priority {priority} and "
                            f"overlapping match with existing rule {baseline_rule.get('rule_id')!r}"
                        ),
                    )
                )
    return conflicts


def _convert_candidate_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Agent Rule Package V1 规则 → 引擎 aggregate rule 可消费格式。

    只补引擎需要的 ``name``（description 回退到 rule_id），不动 match/action/guard。
    """
    converted = dict(rule)
    converted["name"] = (
        str(rule.get("description") or "").strip()
        or str(rule.get("name") or "").strip()
        or str(rule.get("rule_id") or "")
    )
    return converted


def build_candidate_registry(
    baseline_registry: dict[str, Any],
    candidate_package: dict[str, Any],
) -> dict[str, Any]:
    """构造临时 candidate registry：baseline aggregate_rules + candidate rules，保留 sample_rules。"""
    aggregate_rules = list(baseline_registry.get("aggregate_rules") or [])
    for rule in candidate_package.get("rules", []):
        if isinstance(rule, dict):
            aggregate_rules.append(_convert_candidate_rule(rule))
    return {
        "version": baseline_registry.get("version"),
        "policy": baseline_registry.get("policy"),
        "aggregate_rules": aggregate_rules,
        "sample_rules": list(baseline_registry.get("sample_rules") or []),
    }


# ---------------------------------------------------------------------------
# V1 误差函数与判定
# ---------------------------------------------------------------------------


def _positive(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0
    except (TypeError, ValueError):
        return False


def _volume(dims: Any) -> float | None:
    if not isinstance(dims, (list, tuple)) or len(dims) != 3:
        return None
    if not all(_positive(value) for value in dims):
        return None
    return math.prod(float(value) for value in dims)


def volume_error_ratio(predicted_dims: Any, actual_dims: Any) -> float | None:
    predicted = _volume(predicted_dims)
    actual = _volume(actual_dims)
    if predicted is None or actual is None or actual <= 0:
        return None
    return abs(predicted - actual) / actual


def weight_error_ratio(predicted_weight: Any, actual_weight: Any) -> float | None:
    if not _positive(predicted_weight) or not _positive(actual_weight):
        return None
    return abs(float(predicted_weight) - float(actual_weight)) / float(actual_weight)


def record_score(volume_error: float | None, weight_error: float | None) -> float | None:
    values = [value for value in (volume_error, weight_error) if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def evaluate_status(baseline_score: float | None, candidate_score: float | None) -> str:
    if baseline_score is None or candidate_score is None:
        return "insufficient_truth"
    delta = candidate_score - baseline_score
    if delta < -_SCORE_EPSILON:
        return "improved"
    if delta > _SCORE_EPSILON:
        return "degraded"
    return "unchanged"


def scenario_summary(scenario: PackagingScenario) -> dict[str, Any]:
    return {key: getattr(scenario, key) for key in _SCENARIO_SUMMARY_FIELDS}


def _dims_tuple(scenario: PackagingScenario) -> tuple[float, float, float] | None:
    values = (scenario.length_cm, scenario.width_cm, scenario.height_cm)
    if not all(_positive(value) for value in values):
        return None
    return tuple(float(value) for value in values)


# ---------------------------------------------------------------------------
# Replay 执行
# ---------------------------------------------------------------------------


class OfflineCalibrationReplay:
    """同引擎 baseline / candidate 对比 replay（V1）。"""

    def __init__(self, *, expected_engine_version: str | None = None) -> None:
        self.expected_engine_version = (
            str(expected_engine_version).strip()
            if expected_engine_version is not None
            else PackagingEstimationService.ENGINE_VERSION
        )
        self.validator = AgentCalibrationRulePackageValidator(
            expected_engine_version=self.expected_engine_version
        )

    def run(
        self,
        *,
        feedback_manifest: str | Path,
        candidate_package: str | Path,
        baseline_calibration: str | Path,
        baseline_registry: str | Path,
    ) -> dict[str, Any]:
        manifest, manifest_sha256 = load_json_and_hash(feedback_manifest)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("records"), list):
            raise ValueError("feedback manifest must be a JSON object with a 'records' list")
        # ── V2 contract 严格检查 ──
        if manifest.get("contract_version") != "Calibration Feedback Export V2":
            raise ReplayPrecheckError(
                f"feedback manifest contract_version must be 'Calibration Feedback Export V2', "
                f"got {manifest.get('contract_version')!r}"
            )
        package, package_sha256 = load_json_and_hash(candidate_package)
        if not isinstance(package, dict):
            raise ValueError("candidate package must be a JSON object")
        baseline_registry_payload, registry_sha256 = load_json_and_hash(baseline_registry)
        if not isinstance(baseline_registry_payload, dict):
            raise ValueError("baseline registry must be a JSON object")
        _, baseline_calib_sha256 = load_json_and_hash(baseline_calibration)

        # ── batch provenance 检查 ──
        manifest_batch_id = str(manifest.get("export_batch_id") or "")
        source_batch_ids = [
            str(batch_id) for batch_id in package.get("source_export_batch_ids", [])
        ]
        if manifest_batch_id and manifest_batch_id not in source_batch_ids:
            raise ReplayPrecheckError(
                f"candidate package source_export_batch_ids {source_batch_ids!r} "
                f"does not contain manifest export_batch_id {manifest_batch_id!r}"
            )

        validate_candidate(package)
        conflicts = check_candidate_conflicts(package, baseline_registry_payload)
        if conflicts:
            raise ReplayConflictError(conflicts)

        candidate_package_rule_ids = [
            str(rule.get("rule_id")) for rule in package.get("rules", []) if isinstance(rule, dict)
        ]
        baseline_service = PackagingEstimationService(
            baseline_calibration, rule_registry_path=baseline_registry
        )

        # ── baseline calibration version 验证 ──
        runtime_baseline_version = baseline_service.calibration_version
        candidate_declared_base = str(package.get("base_calibration_version") or "")
        if candidate_declared_base and candidate_declared_base != runtime_baseline_version:
            raise ReplayPrecheckError(
                f"candidate declares base_calibration_version={candidate_declared_base!r} "
                f"but runtime baseline calibration version is {runtime_baseline_version!r}"
            )

        input_fingerprints = {
            "feedback_manifest_sha256": manifest_sha256,
            "candidate_package_sha256": package_sha256,
            "baseline_calibration_sha256": baseline_calib_sha256,
            "baseline_registry_sha256": registry_sha256,
        }

        per_record: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="offline-replay-v1-") as temporary_dir:
            candidate_registry = build_candidate_registry(baseline_registry_payload, package)
            temporary_registry = Path(temporary_dir) / "packaging_rule_registry_v1.json"
            temporary_registry.write_text(
                json.dumps(candidate_registry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            candidate_service = PackagingEstimationService(
                baseline_calibration, rule_registry_path=temporary_registry
            )
            for record in manifest["records"]:
                per_record.append(
                    self._replay_record(
                        record,
                        baseline_service=baseline_service,
                        candidate_service=candidate_service,
                        candidate_package_rule_ids=candidate_package_rule_ids,
                    )
                )
        return self._build_result(
            records=manifest["records"],
            per_record=per_record,
            package=package,
            baseline_calibration_version=runtime_baseline_version,
            candidate_declared_base_calibration_version=candidate_declared_base,
            candidate_package_rule_ids=candidate_package_rule_ids,
            input_fingerprints=input_fingerprints,
        )

    # ------------------------------------------------------------------ 单条

    def _replay_record(
        self,
        record: dict[str, Any],
        *,
        baseline_service: PackagingEstimationService,
        candidate_service: PackagingEstimationService,
        candidate_package_rule_ids: list[str],
    ) -> dict[str, Any]:
        record_id = str(record.get("record_id") or "")
        machine_facts = record.get("machine_facts")
        ai_initial = machine_facts.get("ai_initial") if isinstance(machine_facts, dict) else None
        output: dict[str, Any] = {
            "record_id": record_id,
            "candidate_rule_ids": [],
            "status": None,
            "matched": False,
            "applied_profile_ids": [],
            "baseline_normal": None,
            "candidate_normal": None,
            "baseline_conservative": None,
            "candidate_conservative": None,
            "actual_truth": {"dimensions": None, "weight_g": None},
            "baseline_score": None,
            "candidate_score": None,
            "score_delta": None,
            "volume_error_before": None,
            "volume_error_after": None,
            "weight_error_before": None,
            "weight_error_after": None,
        }
        if not isinstance(ai_initial, dict):
            output["status"] = "skipped_ai_initial_missing"
            return output

        # ── 从同一份 ai_initial 分别重建独立对象，防止 estimate() 内部可变修改互相污染 ──
        baseline_observation = rebuild_observation(ai_initial)
        if baseline_observation is None:
            output["status"] = "skipped_ai_initial_missing"
            return output
        candidate_observation = rebuild_observation(ai_initial)
        baseline_external_proposal = rebuild_external_proposal(ai_initial)
        candidate_external_proposal = rebuild_external_proposal(ai_initial)

        baseline_proposal = baseline_service.estimate(
            baseline_observation, external_proposal=baseline_external_proposal,
        )
        candidate_proposal = candidate_service.estimate(
            candidate_observation, external_proposal=candidate_external_proposal,
        )

        truth = extract_truth(machine_facts.get("user_feedback") if isinstance(machine_facts, dict) else None)
        actual_dims = truth.get("dimensions")
        actual_weight = truth.get("weight_g")
        output["actual_truth"] = {"dimensions": actual_dims, "weight_g": actual_weight}
        output["baseline_normal"] = scenario_summary(baseline_proposal.normal)
        output["candidate_normal"] = scenario_summary(candidate_proposal.normal)
        output["baseline_conservative"] = scenario_summary(baseline_proposal.conservative)
        output["candidate_conservative"] = scenario_summary(candidate_proposal.conservative)

        # ── candidate_rule_ids 只保留该记录实际 applied 的候选规则 ──
        applied = set(candidate_proposal.applied_profile_ids)
        output["applied_profile_ids"] = list(candidate_proposal.applied_profile_ids)
        actual_candidate_rule_ids = [
            rule_id for rule_id in candidate_package_rule_ids if rule_id in applied
        ]
        output["candidate_rule_ids"] = actual_candidate_rule_ids
        output["matched"] = bool(actual_candidate_rule_ids)

        actual_dims_tuple: tuple[float, float, float] | None = None
        if isinstance(actual_dims, dict):
            values = (actual_dims.get("length_cm"), actual_dims.get("width_cm"), actual_dims.get("height_cm"))
            if all(_positive(value) for value in values):
                actual_dims_tuple = tuple(float(value) for value in values)

        volume_before = volume_error_ratio(_dims_tuple(baseline_proposal.normal), actual_dims_tuple)
        volume_after = volume_error_ratio(_dims_tuple(candidate_proposal.normal), actual_dims_tuple)
        weight_before = weight_error_ratio(baseline_proposal.normal.weight_g, actual_weight)
        weight_after = weight_error_ratio(candidate_proposal.normal.weight_g, actual_weight)
        baseline_score = record_score(volume_before, weight_before)
        candidate_score = record_score(volume_after, weight_after)
        output["volume_error_before"] = volume_before
        output["volume_error_after"] = volume_after
        output["weight_error_before"] = weight_before
        output["weight_error_after"] = weight_after
        output["baseline_score"] = baseline_score
        output["candidate_score"] = candidate_score
        output["score_delta"] = (
            candidate_score - baseline_score
            if baseline_score is not None and candidate_score is not None
            else None
        )
        output["status"] = evaluate_status(baseline_score, candidate_score)
        return output

    # ------------------------------------------------------------------ 汇总

    @staticmethod
    def _build_result(
        *,
        records: list[dict[str, Any]],
        per_record: list[dict[str, Any]],
        package: dict[str, Any],
        baseline_calibration_version: str,
        candidate_declared_base_calibration_version: str,
        candidate_package_rule_ids: list[str],
        input_fingerprints: dict[str, str],
    ) -> dict[str, Any]:
        judged = {"improved", "unchanged", "degraded"}
        matched = sum(1 for item in per_record if item["status"] != "skipped_ai_initial_missing" and item["matched"])
        unmatched = sum(
            1 for item in per_record if item["status"] != "skipped_ai_initial_missing" and not item["matched"]
        )
        summary = {
            "total_records": len(records),
            "evaluable_records": sum(1 for item in per_record if item["status"] in judged),
            "insufficient_truth": sum(1 for item in per_record if item["status"] == "insufficient_truth"),
            "skipped_ai_initial_missing": sum(
                1 for item in per_record if item["status"] == "skipped_ai_initial_missing"
            ),
            "matched": matched,
            "unmatched": unmatched,
            "improved": sum(1 for item in per_record if item["status"] == "improved"),
            "unchanged": sum(1 for item in per_record if item["status"] == "unchanged"),
            "degraded": sum(1 for item in per_record if item["status"] == "degraded"),
            "conflicts": 0,
        }
        degradations = sorted(
            (
                item for item in per_record
                if item["status"] == "degraded" and item["score_delta"] is not None
            ),
            key=lambda item: float(item["score_delta"]),
            reverse=True,
        )
        largest_degradations = [
            {
                "record_id": item["record_id"],
                "candidate_rule_ids": list(item["candidate_rule_ids"]),
                "baseline_score": item["baseline_score"],
                "candidate_score": item["candidate_score"],
                "score_delta": item["score_delta"],
            }
            for item in degradations[:10]
        ]
        return {
            "replay_version": REPLAY_VERSION,
            "replay_id": uuid4().hex,
            "candidate_package_id": str(package.get("package_id") or ""),
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "baseline_calibration_version": baseline_calibration_version,
            "candidate_declared_base_calibration_version": candidate_declared_base_calibration_version,
            "candidate_package_rule_ids": candidate_package_rule_ids,
            "input_fingerprints": input_fingerprints,
            "summary": summary,
            "largest_degradations": largest_degradations,
            "per_record": per_record,
        }


def run_offline_replay(
    *,
    feedback_manifest: str | Path,
    candidate_package: str | Path,
    baseline_calibration: str | Path,
    baseline_registry: str | Path,
) -> dict[str, Any]:
    """便捷入口：等价于 ``OfflineCalibrationReplay().run(...)``。"""
    return OfflineCalibrationReplay().run(
        feedback_manifest=feedback_manifest,
        candidate_package=candidate_package,
        baseline_calibration=baseline_calibration,
        baseline_registry=baseline_registry,
    )
