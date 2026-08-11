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
    package["source_export_batch_ids"] = ["batch-replay-001"]
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
        baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
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
            calls.append((self, observation, external_proposal))
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
        # 同一 PackagingEstimationService 类、同一 calibration 输入、同一份事实值
        # 但 baseline 与 candidate 收到独立对象（Python 身份不同）
        for index in range(0, 4, 2):
            baseline_obs, candidate_obs = calls[index][1], calls[index + 1][1]
            assert baseline_obs is not candidate_obs
            assert baseline_obs.product_name == candidate_obs.product_name
            baseline_prop, candidate_prop = calls[index][2], calls[index + 1][2]
            if baseline_prop is not None and candidate_prop is not None:
                assert baseline_prop is not candidate_prop
                assert baseline_prop.normal is not candidate_prop.normal
                assert baseline_prop.conservative is not candidate_prop.conservative

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
            baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
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
            baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
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
            "candidate_declared_base_calibration_version",
            "candidate_package_rule_ids",
            "input_fingerprints",
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
                "--baseline-calibration-version", PackagingEstimationService.CALIBRATION_VERSION,
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
                "--baseline-calibration-version", PackagingEstimationService.CALIBRATION_VERSION,
                "--output", str(output),
            ]
        )
        assert exit_code == 1
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["summary"]["conflicts"] == 1
        assert payload["conflicts"][0]["code"] == "duplicate_rule_id"
        assert payload["per_record"] == []

    def test_cli_rejects_missing_baseline_calibration_version(self, tmp_path):
        """CLI 未提供 --baseline-calibration-version → argparse 拒绝"""
        from tools.calibration_offline_replay_v1 import main

        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))])
        output = tmp_path / "replay_result.json"
        with pytest.raises(SystemExit):
            main(
                [
                    "--feedback-manifest", str(paths["manifest"]),
                    "--candidate-package", str(paths["package"]),
                    "--baseline-calibration", str(paths["calibration"]),
                    "--baseline-registry", str(paths["registry"]),
                    "--output", str(output),
                ]
            )

    def test_cli_with_correct_version_runs_successfully(self, tmp_path):
        """CLI 正确提供 --baseline-calibration-version 后可正常运行并写入结果"""
        from tools.calibration_offline_replay_v1 import main

        custom_version = "custom-calibration-version-A"
        package = _candidate_package()
        package["base_calibration_version"] = custom_version
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))], package=package)
        output = tmp_path / "replay_result.json"
        exit_code = main(
            [
                "--feedback-manifest", str(paths["manifest"]),
                "--candidate-package", str(paths["package"]),
                "--baseline-calibration", str(paths["calibration"]),
                "--baseline-registry", str(paths["registry"]),
                "--baseline-calibration-version", custom_version,
                "--output", str(output),
            ]
        )
        assert exit_code == 0
        assert output.is_file()
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["baseline_calibration_version"] == custom_version


# ---------------------------------------------------------------------------
# 新增测试：mutation regression / V2 contract / batch provenance /
# fingerprints / calibration version / candidate_rule_ids 语义
# ---------------------------------------------------------------------------


class TestMutationRegression:
    """确认 baseline estimate 过程中对 observation / external_proposal 的可变修改
    不会污染 candidate estimate 收到的数据。"""

    def test_baseline_mutation_does_not_pollute_candidate(self, tmp_path, monkeypatch):
        """在 baseline estimate 调用中故意修改 observation 和 external_proposal，
        确认 candidate 调用收到的数据仍是原始值。"""
        original = PackagingEstimationService.estimate
        call_log: list[dict] = []

        def spy(self, observation, *, external_proposal=None):
            snapshot = {
                "service": self,
                "product_name": observation.product_name,
                "normal_length": observation.length_cm,
                "proposal_normal_length": (
                    external_proposal.normal.length_cm if external_proposal else None
                ),
            }
            call_log.append(snapshot)
            # 故意在第一次（baseline）调用时修改 observation 和 proposal
            if len(call_log) % 2 == 1:
                observation.product_name = "MUTATED"
                observation.length_cm = 9999.0
                if external_proposal is not None:
                    external_proposal.normal.length_cm = 9999.0
            return original(self, observation, external_proposal=external_proposal)

        monkeypatch.setattr(PackagingEstimationService, "estimate", spy)
        _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        assert len(call_log) == 2
        # baseline 和 candidate 收到的原始值应该相同
        assert call_log[0]["product_name"] == call_log[1]["product_name"] == "scarf 围巾"
        assert call_log[0]["normal_length"] == call_log[1]["normal_length"]
        assert call_log[0]["proposal_normal_length"] == call_log[1]["proposal_normal_length"]
        # candidate 收到的值不应被 baseline 的修改污染
        assert call_log[1]["product_name"] == "scarf 围巾"
        assert call_log[1]["normal_length"] != 9999.0


class TestV2ContractCheck:
    """replay 开始时严格检查 manifest contract_version。"""

    def test_replay_rejects_v1_manifest(self, tmp_path):
        records = [_record("r1", actual=_actual(weight=300))]
        paths = _write_inputs(tmp_path, records)
        # 覆写 manifest 为 V1 contract_version
        manifest_data = {
            "contract_version": "Calibration Feedback Export V1",
            "export_batch_id": "batch-replay-001",
            "exported_at": "2026-08-11T00:00:00Z",
            "records": records,
        }
        paths["manifest"].write_text(json.dumps(manifest_data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ReplayPrecheckError, match="contract_version"):
            OfflineCalibrationReplay().run(
                feedback_manifest=paths["manifest"],
                candidate_package=paths["package"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
            )

    def test_replay_rejects_unknown_contract_version(self, tmp_path):
        records = [_record("r1", actual=_actual(weight=300))]
        paths = _write_inputs(tmp_path, records)
        manifest_data = {
            "contract_version": "unknown-version",
            "export_batch_id": "batch-replay-001",
            "exported_at": "2026-08-11T00:00:00Z",
            "records": records,
        }
        paths["manifest"].write_text(json.dumps(manifest_data, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ReplayPrecheckError, match="contract_version"):
            OfflineCalibrationReplay().run(
                feedback_manifest=paths["manifest"],
                candidate_package=paths["package"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
            )

    def test_replay_accepts_v2_manifest(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual(weight=300))],
        )
        assert result["replay_version"] == "offline-replay-v1"


class TestBatchProvenance:
    """candidate package 的 source_export_batch_ids 必须包含 manifest 的 export_batch_id。"""

    def test_batch_match_runs_normally(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual(weight=300))],
        )
        assert result["summary"]["total_records"] == 1

    def test_batch_mismatch_rejects_replay(self, tmp_path):
        records = [_record("r1", actual=_actual(weight=300))]
        paths = _write_inputs(tmp_path, records)
        # 覆写 candidate package 的 source_export_batch_ids 为不包含 manifest batch
        package = _candidate_package()
        package["source_export_batch_ids"] = ["batch-other-999"]
        paths["package"].write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ReplayPrecheckError, match="source_export_batch_ids"):
            OfflineCalibrationReplay().run(
                feedback_manifest=paths["manifest"],
                candidate_package=paths["package"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
            )


class TestInputFingerprints:
    """replay_result.json 必须包含 4 个 SHA-256 指纹。"""

    def test_four_hashes_present_and_valid_hex(self, tmp_path):
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        fingerprints = result["input_fingerprints"]
        expected_keys = {
            "feedback_manifest_sha256",
            "candidate_package_sha256",
            "baseline_calibration_sha256",
            "baseline_registry_sha256",
        }
        assert set(fingerprints) == expected_keys
        for key in expected_keys:
            value = fingerprints[key]
            assert isinstance(value, str)
            assert len(value) == 64
            assert all(c in "0123456789abcdef" for c in value)

    def test_hash_changes_when_input_bytes_change(self, tmp_path):
        result1, paths1 = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
        )
        # 修改 manifest 内容（增加一条记录），重新运行
        run2_dir = tmp_path / "run2"
        run2_dir.mkdir()
        records = [
            _record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300)),
            _record("r2", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300)),
        ]
        paths2 = _write_inputs(run2_dir, records)
        result2 = OfflineCalibrationReplay().run(
            feedback_manifest=paths2["manifest"],
            candidate_package=paths2["package"],
            baseline_calibration=paths2["calibration"],
            baseline_registry=paths2["registry"],
            baseline_calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
        )
        # manifest 内容不同 → hash 不同
        assert result1["input_fingerprints"]["feedback_manifest_sha256"] != result2["input_fingerprints"]["feedback_manifest_sha256"]


class TestCalibrationVersionValidation:
    """baseline_calibration_version 必须由显式参数传入，不依赖 Service 默认常量。"""

    def test_explicit_version_used_as_baseline(self, tmp_path):
        """显式传入 custom-version-A → replay_result.baseline_calibration_version == custom-version-A"""
        custom_version = "custom-calibration-version-A"
        # 同时让 candidate 声明相同版本以通过校验
        package = _candidate_package()
        package["base_calibration_version"] = custom_version
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))], package=package)
        result = OfflineCalibrationReplay().run(
            feedback_manifest=paths["manifest"],
            candidate_package=paths["package"],
            baseline_calibration=paths["calibration"],
            baseline_registry=paths["registry"],
            baseline_calibration_version=custom_version,
        )
        assert result["baseline_calibration_version"] == custom_version

    def test_both_services_receive_explicit_version(self, tmp_path, monkeypatch):
        """两个 PackagingEstimationService 实际收到 calibration_version == custom-version-A"""
        custom_version = "custom-calibration-version-A"
        package = _candidate_package()
        package["base_calibration_version"] = custom_version
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))], package=package)

        calls: list = []
        original_init = PackagingEstimationService.__init__

        def wrapped_init(self, calibration_path=None, *, calibration_version=None, rule_registry_path=None):
            calls.append(calibration_version)
            return original_init(self, calibration_path, calibration_version=calibration_version, rule_registry_path=rule_registry_path)

        monkeypatch.setattr(PackagingEstimationService, "__init__", wrapped_init)
        OfflineCalibrationReplay().run(
            feedback_manifest=paths["manifest"],
            candidate_package=paths["package"],
            baseline_calibration=paths["calibration"],
            baseline_registry=paths["registry"],
            baseline_calibration_version=custom_version,
        )
        # baseline 和 candidate 两个 Service 都应收到 custom_version
        assert len(calls) >= 2
        assert calls[0] == custom_version
        assert calls[1] == custom_version

    def test_candidate_matching_version_accepted(self, tmp_path):
        """candidate base_calibration_version == custom-version-A → 正常"""
        custom_version = "custom-calibration-version-A"
        package = _candidate_package()
        package["base_calibration_version"] = custom_version
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))], package=package)
        result = OfflineCalibrationReplay().run(
            feedback_manifest=paths["manifest"],
            candidate_package=paths["package"],
            baseline_calibration=paths["calibration"],
            baseline_registry=paths["registry"],
            baseline_calibration_version=custom_version,
        )
        assert result["baseline_calibration_version"] == custom_version
        assert result["candidate_declared_base_calibration_version"] == custom_version

    def test_candidate_mismatched_version_rejected(self, tmp_path):
        """candidate 声明 custom-version-B，baseline 显式 custom-version-A → ReplayPrecheckError"""
        package = _candidate_package()
        package["base_calibration_version"] = "custom-calibration-version-B"
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))], package=package)
        with pytest.raises(ReplayPrecheckError, match="base_calibration_version"):
            OfflineCalibrationReplay().run(
                feedback_manifest=paths["manifest"],
                candidate_package=paths["package"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version="custom-calibration-version-A",
            )

    def test_empty_version_rejected(self, tmp_path):
        """空字符串 baseline_calibration_version → ValueError"""
        paths = _write_inputs(tmp_path, [_record("r1", actual=_actual(weight=300))])
        with pytest.raises(ValueError, match="non-empty"):
            OfflineCalibrationReplay().run(
                feedback_manifest=paths["manifest"],
                candidate_package=paths["package"],
                baseline_calibration=paths["calibration"],
                baseline_registry=paths["registry"],
                baseline_calibration_version="",
            )


class TestCandidateRuleIdsSemantics:
    """candidate_rule_ids 只保留该记录实际 applied 的候选规则。"""

    def test_per_record_only_includes_applied_rules(self, tmp_path):
        """candidate 包包含 A、B 两条规则，记录只命中 A，
        per_record.candidate_rule_ids 必须只包含 A，不包含 B。"""
        rule_a = _candidate_rule(
            "AGR-REPLAY-A",
            match={"any_terms": ["scarf"], "rigidity": ["soft"], "foldability": ["good"], "forbid_hard_structure": True},
            action={"type": "smallest_axis_scale", "normal": 0.6, "conservative": 0.75, "min_cm": 1.0},
        )
        rule_b = _candidate_rule(
            "AGR-REPLAY-B",
            match={"any_terms": ["no_such_product_xyz"]},
            action={"type": "smallest_axis_add", "normal_cm": 1.0, "conservative_cm": 2.0},
        )
        package = _candidate_package()
        package["rules"] = [rule_a, rule_b]
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
            package=package,
        )
        entry = result["per_record"][0]
        # A 应该被 applied，B 不应该
        assert "AGR-REPLAY-A" in entry["candidate_rule_ids"]
        assert "AGR-REPLAY-B" not in entry["candidate_rule_ids"]
        # 顶层 candidate_package_rule_ids 包含整包规则
        assert "AGR-REPLAY-A" in result["candidate_package_rule_ids"]
        assert "AGR-REPLAY-B" in result["candidate_package_rule_ids"]
        # matched 基于实际 applied 的 candidate rules
        assert entry["matched"] is True

    def test_no_match_means_empty_candidate_rule_ids(self, tmp_path):
        """candidate 规则完全不匹配时，per_record.candidate_rule_ids 为空。"""
        package = _candidate_package(
            _candidate_rule("AGR-REPLAY-NOMATCH", match={"any_terms": ["no_such_product"]})
        )
        result, _paths = _run(
            tmp_path,
            [_record("r1", actual=_actual({"length_cm": 30, "width_cm": 29, "height_cm": 6}, 300))],
            package=package,
        )
        entry = result["per_record"][0]
        assert entry["candidate_rule_ids"] == []
        assert entry["matched"] is False
        # 顶层仍包含整包规则 ID
        assert "AGR-REPLAY-NOMATCH" in result["candidate_package_rule_ids"]
