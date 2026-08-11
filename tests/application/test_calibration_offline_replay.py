"""Offline Replay V1 独立测试。

覆盖：
- 合法 V2 manifest + candidate 可运行；
- candidate validator 不通过时拒绝 replay；
- baseline 与 candidate 确实调用同一 PackagingEstimationService（同一 observation 输入）；
- candidate rule 可以改变结果；improved / degraded / unchanged；
- insufficient_truth：尺寸与重量都缺失、fee-only 不参与包装评分；
- actual dimensions only / actual package weight only / dimensions + weight；
- legacy / ai_initial=null 安全跳过；
- 重复 rule_id、同 priority 重叠冲突；
- 临时 candidate registry 不污染 baseline；正式 calibration 文件未修改；
- output JSON 可解析。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_offline_replay import (
    OfflineCalibrationReplay,
    ReplayConflictError,
    ReplayPrecheckError,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_CANDIDATE = REPO_ROOT / "docs" / "contracts" / "agent_calibration_rule_package_v1.example.json"


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


def _candidate_rule(
    rule_id: str,
    *,
    match: dict | None = None,
    action: dict | None = None,
    priority: int = 95,
) -> dict:
    return {
        "rule_id": rule_id,
        "enabled": True,
        "priority": priority,
        "description": f"{rule_id} replay 测试规则",
        "match": match or {
            "any_terms": ["scarf"],
            "rigidity": ["soft"],
            "foldability": ["good"],
            "forbid_hard_structure": True,
        },
        "action": action or {
            "type": "smallest_axis_scale",
            "normal": 0.6,
            "conservative": 0.75,
            "min_cm": 1.0,
        },
        "evidence": {"source_record_ids": ["record-1"], "sample_count": 1, "rationale": "replay test"},
    }


def _candidate_package(rule: dict | None = None) -> dict:
    package = json.loads(EXAMPLE_CANDIDATE.read_text(encoding="utf-8"))
    package["package_id"] = "cal-replay-test-001"
    package["rules"] = [rule] if rule is not None else [_candidate_rule("AGR-REPLAY-SCARF-001")]
    return package


def _observation(**overrides) -> dict:
    observation = {
        "product_name": "scarf 围巾",
        "product_type": "scarf",
        "material": "cotton",
        "rigidity": "soft",
        "foldability": "good",
        "compressibility": "good",
        "length_cm": 30,
        "width_cm": 30,
        "height_cm": 10,
        "weight_g": 300,
        "dimension_scope": "product_size",
        "weight_scope": "net_weight",
        "packaging_state_hint": "moderate_compression",
        "confidence": "low",
    }
    observation.update(overrides)
    return observation


def _scenario(dims: tuple[float, float, float], weight: float, method: str = "袋装") -> dict:
    return {
        "packaging_state": "moderate_compression",
        "packaging_method": method,
        "length_cm": dims[0],
        "width_cm": dims[1],
        "height_cm": dims[2],
        "weight_g": weight,
        "reasoning_summary": "ai",
        "confidence": "low",
        "needs_review": True,
        "default_fields_used": [],
    }


def _packaging_proposal() -> dict:
    return {
        "source_kind": "external_ai_packaging_proposal",
        "normal": _scenario((32, 30, 8), 320),
        "conservative": _scenario((33, 31, 9), 340),
        "engine_version": PackagingEstimationService.ENGINE_VERSION,
        "calibration_version": "local-calibration-v3-77-samples-rules-v1",
    }


def _feedback(actual_logistics: dict | None = None) -> dict:
    return {
        "feedback_id": "fb-replay-001",
        "feedback_schema_version": "calibration-feedback-v1",
        "source": "user",
        "created_at": "2026-08-11T00:00:00Z",
        "updated_at": "2026-08-11T00:00:00Z",
        "structure": {
            "can_fold": "unknown",
            "can_compress": "unknown",
            "can_coil": "unknown",
            "can_disassemble": "unknown",
            "requires_shape_retention": "unknown",
            "foldable_parts": [],
            "compressible_parts": [],
            "coilable_parts": [],
            "detachable_parts": [],
            "rigid_parts": [],
            "axis_behavior": {"length": "unknown", "width": "unknown", "height": "unknown"},
        },
        "suggested_package": None,
        "actual_logistics": actual_logistics,
        "user_note": None,
    }


def _record(
    record_id: str,
    *,
    ai_initial: dict | None = None,
    feedback: dict | None = None,
    actual: dict | None = None,
) -> dict:
    if ai_initial is None:
        ai_initial = {
            "observation": _observation(),
            "packaging_proposal": _packaging_proposal(),
        }
    if feedback is None:
        feedback = _feedback(actual)
    return {
        "sequence": 1,
        "record_id": record_id,
        "product_short_name": "scarf",
        "product_link": "",
        "main_image": "",
        "images": [],
        "ai_initial_shipment": "",
        "user_calibration": "",
        "actual_first_mile": "",
        "machine_facts": {"ai_initial": ai_initial, "user_feedback": feedback},
    }


def _manifest(records: list[dict]) -> dict:
    return {
        "contract_version": "Calibration Feedback Export V2",
        "export_batch_id": "batch-replay-001",
        "exported_at": "2026-08-11T00:00:00Z",
        "records": records,
    }


def _write_inputs(
    tmp_path: Path,
    records: list[dict],
    *,
    package: dict | None = None,
    baseline_aggregate: list[dict] | None = None,
    samples: list[dict] | None = None,
) -> dict[str, Path]:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(records), ensure_ascii=False), encoding="utf-8")
    package_path = tmp_path / "candidate.json"
    package_path.write_text(json.dumps(package or _candidate_package(), ensure_ascii=False), encoding="utf-8")
    calibration_path = tmp_path / "baseline_calibration.json"
    calibration_path.write_text(
        json.dumps(samples if samples is not None else [{"sample_id": "S1"}]),
        encoding="utf-8",
    )
    registry_path = tmp_path / "baseline_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "v1",
                "policy": {},
                "aggregate_rules": list(baseline_aggregate or []),
                "sample_rules": [],
            }
        ),
        encoding="utf-8",
    )
    return {
        "manifest": manifest_path,
        "package": package_path,
        "calibration": calibration_path,
        "registry": registry_path,
    }


def _run(tmp_path: Path, records: list[dict], **kwargs) -> tuple[dict, dict[str, Path]]:
    paths = _write_inputs(tmp_path, records, **kwargs)
    result = OfflineCalibrationReplay().run(
        feedback_manifest=paths["manifest"],
        candidate_package=paths["package"],
        baseline_calibration=paths["calibration"],
        baseline_registry=paths["registry"],
    )
    return result, paths


def _actual(dimensions: dict | None = None, weight: float | None = None) -> dict:
    actual: dict = {}
    if dimensions is not None:
        actual["actual_package_dimensions"] = dimensions
    if weight is not None:
        actual["actual_package_weight_g"] = weight
    return actual


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


class TestReplayExecution:
    def test_legal_v2_manifest_and_candidate_runs(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        assert result["replay_version"] == "offline-replay-v1"
        assert result["candidate_package_id"] == "cal-replay-test-001"
        assert result["engine_version"] == PackagingEstimationService.ENGINE_VERSION
        assert result["summary"]["total_records"] == 1
        assert result["summary"]["evaluable_records"] == 1
        assert result["summary"]["conflicts"] == 0
        assert result["per_record"][0]["status"] in {"improved", "unchanged", "degraded"}

    def test_replay_rejected_when_candidate_invalid(self, tmp_path):
        package = _candidate_package()
        package["base_engine_version"] = "wrong-engine"
        with pytest.raises(ReplayPrecheckError):
            _run(tmp_path, [_record("r1")], package=package)

    def test_replay_rejects_non_candidate_status(self, tmp_path):
        package = _candidate_package()
        package["status"] = "validated"
        package["validation"] = {
            "validator": "offline-replay-v1",
            "replay_id": "replay-x",
            "engine_version": PackagingEstimationService.ENGINE_VERSION,
            "total_records": 1,
            "matched": 1,
            "improved": 1,
            "unchanged": 0,
            "degraded": 0,
            "conflicts": 0,
        }
        with pytest.raises(ReplayPrecheckError):
            _run(tmp_path, [_record("r1")], package=package)

    def test_baseline_and_candidate_use_same_engine(self, tmp_path, monkeypatch):
        calls: list = []
        original = PackagingEstimationService.estimate

        def wrapped(self, observation, *, external_proposal=None):
            calls.append((self, observation))
            return original(self, observation, external_proposal=external_proposal)

        monkeypatch.setattr(PackagingEstimationService, "estimate", wrapped)
        _run(
            tmp_path,
            [
                _record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300)),
                _record("r2", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300)),
            ],
        )
        assert len(calls) == 4
        baseline_service, candidate_service = calls[0][0], calls[1][0]
        assert isinstance(baseline_service, PackagingEstimationService)
        assert isinstance(candidate_service, PackagingEstimationService)
        assert baseline_service.calibration_path == candidate_service.calibration_path
        assert baseline_service.rule_registry_path != candidate_service.rule_registry_path
        for index in range(0, 4, 2):
            assert calls[index][1] is calls[index + 1][1]

    def test_candidate_rule_can_change_result(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        entry = result["per_record"][0]
        assert entry["matched"] is True
        assert "AGR-REPLAY-SCARF-001" in entry["applied_profile_ids"]
        assert entry["candidate_normal"]["height_cm"] != entry["baseline_normal"]["height_cm"]

    def test_improved(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        entry = result["per_record"][0]
        assert entry["status"] == "improved"
        assert entry["baseline_score"] is not None
        assert entry["score_delta"] < 0
        assert result["summary"]["improved"] == 1
        assert result["summary"]["degraded"] == 0

    def test_degraded(self, tmp_path):
        package = _candidate_package(
            _candidate_rule(
                "AGR-REPLAY-SCARF-ADD",
                action={"type": "smallest_axis_add", "normal_cm": 3.0, "conservative_cm": 4.0},
            )
        )
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
            package=package,
        )
        entry = result["per_record"][0]
        assert entry["status"] == "degraded"
        assert entry["score_delta"] > 0
        assert result["summary"]["degraded"] == 1
        assert result["largest_degradations"][0]["record_id"] == "r1"

    def test_unchanged_when_candidate_rule_does_not_match(self, tmp_path):
        package = _candidate_package(
            _candidate_rule("AGR-REPLAY-NOMATCH", match={"any_terms": ["no-such-product"]})
        )
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
            package=package,
        )
        entry = result["per_record"][0]
        assert entry["matched"] is False
        assert entry["status"] == "unchanged"
        assert entry["score_delta"] == 0
        assert result["summary"]["unmatched"] == 1
        assert result["summary"]["unchanged"] == 1


class TestTruthAndScoring:
    def test_insufficient_truth_when_no_dimensions_and_no_weight(self, tmp_path):
        result, _paths = _run(tmp_path, [_record("r1", actual=None)])
        entry = result["per_record"][0]
        assert entry["status"] == "insufficient_truth"
        assert entry["baseline_score"] is None
        assert entry["candidate_score"] is None
        assert entry["volume_error_before"] is None
        assert entry["weight_error_before"] is None
        assert result["summary"]["insufficient_truth"] == 1
        assert result["summary"]["evaluable_records"] == 0

    def test_fee_only_does_not_participate_in_packaging_score(self, tmp_path):
        actual = {
            "actual_first_mile_fee_rmb": 26.0,
            "actual_chargeable_weight_kg": 0.53,
            "evidence_level": "actual_logistics",
        }
        result, _paths = _run(tmp_path, [_record("r1", actual=actual)])
        entry = result["per_record"][0]
        assert entry["status"] == "insufficient_truth"
        assert entry["baseline_score"] is None
        assert entry["candidate_score"] is None
        assert entry["actual_truth"]["dimensions"] is None
        assert entry["actual_truth"]["weight_g"] is None

    def test_actual_dimensions_only(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}))],
        )
        entry = result["per_record"][0]
        assert entry["volume_error_before"] is not None
        assert entry["volume_error_after"] is not None
        assert entry["weight_error_before"] is None
        assert entry["weight_error_after"] is None
        assert entry["baseline_score"] == pytest.approx(entry["volume_error_before"])
        assert entry["candidate_score"] == pytest.approx(entry["volume_error_after"])

    def test_actual_package_weight_only(self, tmp_path):
        result, _paths = _run(tmp_path, [_record("r1", actual=_actual(weight=300))])
        entry = result["per_record"][0]
        assert entry["volume_error_before"] is None
        assert entry["volume_error_after"] is None
        assert entry["weight_error_before"] is not None
        assert entry["weight_error_after"] is not None
        assert entry["baseline_score"] == pytest.approx(entry["weight_error_before"])
        assert entry["candidate_score"] == pytest.approx(entry["weight_error_after"])

    def test_dimensions_and_weight(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        entry = result["per_record"][0]
        assert entry["volume_error_before"] is not None
        assert entry["weight_error_before"] is not None
        assert entry["baseline_score"] == pytest.approx(
            (entry["volume_error_before"] + entry["weight_error_before"]) / 2
        )
        assert entry["candidate_score"] == pytest.approx(
            (entry["volume_error_after"] + entry["weight_error_after"]) / 2
        )

    def test_legacy_ai_initial_null_skipped_safely(self, tmp_path):
        legacy = _record("legacy-1")
        legacy["machine_facts"] = {"ai_initial": None, "user_feedback": None}
        result, _paths = _run(tmp_path, [legacy, _record("r1", actual=_actual(weight=300))])
        assert result["per_record"][0]["status"] == "skipped_ai_initial_missing"
        assert result["per_record"][0]["baseline_score"] is None
        assert result["per_record"][0]["candidate_score"] is None
        assert result["summary"]["total_records"] == 2
        assert result["summary"]["evaluable_records"] == 1
        assert result["summary"]["skipped_ai_initial_missing"] == 1


class TestConflicts:
    def _baseline_rule(self, rule_id: str, priority: int = 95) -> dict:
        return {
            "rule_id": rule_id,
            "enabled": True,
            "priority": priority,
            "name": f"{rule_id} baseline rule",
            "match": {"any_terms": ["scarf"], "rigidity": ["soft"]},
            "action": {"type": "smallest_axis_add", "normal_cm": 1.0, "conservative_cm": 2.0},
        }

    def test_existing_rule_id_conflict(self, tmp_path):
        baseline_aggregate = [self._baseline_rule("AGR-REPLAY-SCARF-001")]
        with pytest.raises(ReplayConflictError) as exc_info:
            _run(tmp_path, [_record("r1")], baseline_aggregate=baseline_aggregate)
        assert any(conflict.code == "duplicate_rule_id" for conflict in exc_info.value.conflicts)

    def test_same_priority_overlap_conflict(self, tmp_path):
        baseline_aggregate = [self._baseline_rule("AGR-BASE-SOFT-001", priority=95)]
        with pytest.raises(ReplayConflictError) as exc_info:
            _run(tmp_path, [_record("r1")], baseline_aggregate=baseline_aggregate)
        assert any(conflict.code == "same_priority_overlap" for conflict in exc_info.value.conflicts)

    def test_same_priority_disjoint_match_is_not_a_conflict(self, tmp_path):
        baseline_aggregate = [
            {
                "rule_id": "AGR-BASE-BOX-001",
                "enabled": True,
                "priority": 95,
                "name": "box rule",
                "match": {"any_terms": ["cardboard box"]},
                "action": {"type": "smallest_axis_add", "normal_cm": 1.0, "conservative_cm": 2.0},
            }
        ]
        result, _paths = _run(tmp_path, [_record("r1")], baseline_aggregate=baseline_aggregate)
        assert result["summary"]["conflicts"] == 0


class TestIsolation:
    def test_temp_candidate_registry_cleaned_and_does_not_pollute_baseline(self, tmp_path, monkeypatch):
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))])
        calibration_before = paths["calibration"].read_bytes()
        registry_before = paths["registry"].read_bytes()
        calls: list = []
        original = PackagingEstimationService.estimate

        def wrapped(self, observation, *, external_proposal=None):
            calls.append(self)
            return original(self, observation, external_proposal=external_proposal)

        monkeypatch.setattr(PackagingEstimationService, "estimate", wrapped)
        OfflineCalibrationReplay().run(
            feedback_manifest=paths["manifest"],
            candidate_package=paths["package"],
            baseline_calibration=paths["calibration"],
            baseline_registry=paths["registry"],
        )
        candidate_service = calls[1]
        assert candidate_service.rule_registry_path != paths["registry"]
        assert not candidate_service.rule_registry_path.exists()
        assert paths["calibration"].read_bytes() == calibration_before
        assert paths["registry"].read_bytes() == registry_before

    def test_replay_does_not_modify_formal_calibration_files(self, tmp_path):
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))])
        calibration_before = paths["calibration"].read_bytes()
        registry_before = paths["registry"].read_bytes()
        OfflineCalibrationReplay().run(
            feedback_manifest=paths["manifest"],
            candidate_package=paths["package"],
            baseline_calibration=paths["calibration"],
            baseline_registry=paths["registry"],
        )
        assert paths["calibration"].read_bytes() == calibration_before
        assert paths["registry"].read_bytes() == registry_before

    def test_output_json_is_parseable(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        serialized = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["replay_version"] == "offline-replay-v1"
        assert set(parsed) == {
            "replay_version",
            "replay_id",
            "candidate_package_id",
            "engine_version",
            "baseline_calibration_version",
            "summary",
            "largest_degradations",
            "per_record",
        }
        required_record_keys = {
            "record_id",
            "candidate_rule_ids",
            "status",
            "baseline_normal",
            "candidate_normal",
            "baseline_conservative",
            "candidate_conservative",
            "actual_truth",
            "baseline_score",
            "candidate_score",
            "score_delta",
            "volume_error_before",
            "volume_error_after",
            "weight_error_before",
            "weight_error_after",
        }
        assert required_record_keys <= set(parsed["per_record"][0])


class TestCli:
    def test_cli_writes_parseable_output(self, tmp_path):
        from tools.calibration_offline_replay_v1 import main

        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))])
        output = tmp_path / "replay_result.json"
        exit_code = main(
            [
                "--feedback-manifest", str(paths["manifest"]),
                "--candidate-package", str(paths["package"]),
                "--baseline-calibration", str(paths["calibration"]),
                "--baseline-registry", str(paths["registry"]),
                "--output", str(output),
            ]
        )
        assert exit_code == 0
        assert output.is_file()
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["replay_version"] == "offline-replay-v1"
        assert payload["summary"]["total_records"] == 1

    def test_cli_writes_conflict_output_and_stops(self, tmp_path):
        from tools.calibration_offline_replay_v1 import main

        baseline_aggregate = [
            {
                "rule_id": "AGR-REPLAY-SCARF-001",
                "enabled": True,
                "priority": 95,
                "name": "dup",
                "match": {"any_terms": ["scarf"]},
                "action": {"type": "smallest_axis_add", "normal_cm": 1.0, "conservative_cm": 2.0},
            }
        ]
        paths = _write_inputs(tmp_path, [_record("r1")], baseline_aggregate=baseline_aggregate)
        output = tmp_path / "replay_conflict.json"
        exit_code = main(
            [
                "--feedback-manifest", str(paths["manifest"]),
                "--candidate-package", str(paths["package"]),
                "--baseline-calibration", str(paths["calibration"]),
                "--baseline-registry", str(paths["registry"]),
                "--output", str(output),
            ]
        )
        assert exit_code == 1
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["summary"]["conflicts"] == 1
        assert payload["conflicts"][0]["code"] == "duplicate_rule_id"
        assert payload["per_record"] == []
