"""CAL77 Conservative Migration V1 contract and runtime behavior tests.

验证 packaging_rule_registry_v1.json 收紧后的合同，以及
PackagingEstimationService 在新 builtin registry 下的真实生产行为：
- 77 条历史 sample_rules 全部退出 runtime（enabled=false）
- 仅 AGR-THIN-TEXTILE-001 保留为低置信 legacy numeric fallback
- 历史坏样本（after_actual/unknown）不再有任何生产影响路径
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation


ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "calibration/logistics_v2/calibration_all_cleaned_v3.json"
REGISTRY = ROOT / "calibration/logistics_v2/packaging_rule_registry_v1.json"


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def service() -> PackagingEstimationService:
    return PackagingEstimationService(CALIBRATION, rule_registry_path=REGISTRY)


def no_hard_kwargs() -> dict:
    return dict(
        has_hard_bottom=False, has_hard_backboard=False, has_frame=False,
        has_rigid_insert=False, has_rigid_parts=False, retail_box_visible=False,
        hard_card_visible=False,
    )


# ===========================================================================
# Migration contract（registry JSON 层面）
# ===========================================================================


class TestConservativeRegistryContract:
    def test_calibration_samples_remain_77_and_byte_unchanged(self):
        # 历史样本档案字节级未修改
        digest = hashlib.sha256(CALIBRATION.read_bytes()).hexdigest()
        assert digest == "ae10226731d006a4ad540e6c6d9fc5224067823140cfbc34e408984529d6ad0d"
        samples = json.loads(CALIBRATION.read_text(encoding="utf-8"))
        assert len(samples) == 77

    def test_sample_rules_keep_77_entries_all_disabled(self, registry):
        sample_rules = registry["sample_rules"]
        assert len(sample_rules) == 77
        assert {item["rule_id"] for item in sample_rules} == {f"CAL-{i:03d}" for i in range(1, 78)}
        assert all(item["enabled"] is False for item in sample_rules)

    def test_sample_rule_roles_keep_original_historical_semantics(self, registry):
        roles = {item["role"] for item in registry["sample_rules"]}
        # 原有三种历史 role 均保留，未被整体重写
        assert roles == {"numeric_reference", "experience_reference", "guard_only"}

    def test_aggregate_rules_keep_9_entries(self, registry):
        assert len(registry["aggregate_rules"]) == 9

    def test_enabled_aggregate_ids_strictly_thin_textile_only(self, registry):
        enabled = [item["rule_id"] for item in registry["aggregate_rules"] if item["enabled"]]
        assert enabled == ["AGR-THIN-TEXTILE-001"]

    def test_thin_textile_is_low_confidence_and_needs_review(self, registry):
        rule = next(item for item in registry["aggregate_rules"] if item["rule_id"] == "AGR-THIN-TEXTILE-001")
        assert rule["enabled"] is True
        assert rule["confidence"] == "low"
        assert rule["needs_review"] is True
        # action 参数保持原值，未重新调参
        assert rule["action"] == {"type": "smallest_axis_scale", "normal": 0.75, "conservative": 0.9, "min_cm": 1.5}
        # reason 明确声明低置信且不视为新闭环 validated 规则
        assert "低置信" in rule["reason"]
        assert "不视为新闭环 validated 规则" in rule["reason"]

    def test_other_8_aggregates_disabled_with_migration_reason(self, registry):
        disabled = [item for item in registry["aggregate_rules"] if item["rule_id"] != "AGR-THIN-TEXTILE-001"]
        assert len(disabled) == 8
        for item in disabled:
            assert item["enabled"] is False, item["rule_id"]
            assert item.get("migration_status") == "legacy_reference_only", item["rule_id"]
            assert item.get("migration_reason"), item["rule_id"]
            # action 与历史字段保留，仅停用
            assert item.get("action"), item["rule_id"]
            assert item.get("source_cal_ids"), item["rule_id"]

    def test_policy_is_conservative(self, registry):
        policy = registry["policy"]
        assert policy["single_sample_enabled"] is False
        assert policy["all_records_have_runtime_role"] is False
        # 仍成立的既有 policy 未被删除
        assert policy["external_ai_packaging_is_reference_only"] is True
        assert policy["user_confirmed_shipping_data_is_authoritative"] is True
        assert policy["conservative_must_not_be_lower_than_normal"] is True

    def test_registry_version_tracks_migration(self, registry):
        assert registry["version"] == "packaging-rules-v2-cal77-conservative"


# ===========================================================================
# Runtime behavior（真实 PackagingEstimationService）
# ===========================================================================


class TestLegacySampleRulesExitRuntime:
    def test_cal001_strong_match_no_longer_produces_numeric_candidate(self, service):
        # CAL-001 过去可形成 strong sample match
        observation = AIObservation(
            product_type="flat_top_military_cap", material="cotton_canvas",
            rigidity="semi_rigid", requires_shape_retention=True,
            length_cm=25, width_cm=20, height_cm=11, weight_g=80,
            weight_scope="packaged_weight", **no_hard_kwargs(),
        )
        result = service.estimate(observation)
        assert "CAL-001" not in result.applied_profile_ids
        matches = result.candidate_records["cal_match_audit"]["sample_matches"]
        assert all(item["rule_id"] != "CAL-001" for item in matches)
        cal_candidate = result.candidate_records.get("cal_candidate")
        if cal_candidate:
            assert "CAL-001" not in (cal_candidate.get("matched_rule_ids") or [])

    def test_no_sample_rule_can_reach_runtime_matching(self, service):
        # 任何历史 sample 都不再进入 sample 匹配循环
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for rule in registry["sample_rules"]:
            observation = AIObservation(
                product_type=rule["product_type"], material=rule.get("material") or "",
                rigidity=rule.get("rigidity") or "unknown",
                requires_shape_retention=rule.get("requires_shape_retention"),
            )
            result = service.estimate(observation)
            assert result.candidate_records["cal_match_audit"]["sample_matches"] == [], rule["rule_id"]


class TestSingleSampleAggregatesExitRuntime:
    def test_pu_handbag_no_longer_scaled_by_disabled_aggregate(self, service):
        # 过去 AGR-PU-BAG-065 会把厚度轴 ×0.65
        observation = AIObservation(
            product_name="soft PU handbag", product_type="handbag", material="pu",
            rigidity="soft", foldability="limited", compressibility="limited",
            length_cm=30, width_cm=20, height_cm=10, weight_g=300,
            weight_scope="packaged_weight", **no_hard_kwargs(),
        )
        result = service.estimate(observation)
        assert "AGR-PU-BAG-065" not in result.applied_profile_ids
        assert result.normal.height_cm != 6.5  # 未被 ×0.65 改写
        assert result.normal.height_cm == 10.0

    def test_pvc_thin_no_longer_template_scaled(self, service):
        # 过去 AGR-PVC-THIN-068 会输出固定模板 10×10×3
        observation = AIObservation(
            product_name="透明PVC化妆包", product_type="transparent_cosmetic_bag", material="pvc",
            rigidity="soft", foldability="good", compressibility="good",
            length_cm=22, width_cm=11, height_cm=18, weight_g=100,
            weight_scope="packaged_weight", **no_hard_kwargs(),
        )
        result = service.estimate(observation)
        assert "AGR-PVC-THIN-068" not in result.applied_profile_ids
        assert (result.normal.length_cm, result.normal.width_cm, result.normal.height_cm) != (10.0, 10.0, 3.0)

    def test_oxford_backpack_no_longer_compressed(self, service):
        # 过去 AGR-OXFORD-BACKPACK-076 会把厚度轴 ×0.4
        observation = AIObservation(
            product_name="oxford backpack", product_type="backpack", material="oxford",
            rigidity="soft", foldability="limited", compressibility="limited",
            length_cm=40, width_cm=30, height_cm=15, weight_g=500,
            weight_scope="packaged_weight", **no_hard_kwargs(),
        )
        result = service.estimate(observation)
        assert "AGR-OXFORD-BACKPACK-076" not in result.applied_profile_ids
        assert result.normal.height_cm != 6.0  # 未被 ×0.4 改写
        assert result.normal.height_cm == 15.0


class TestThinTextileLegacyFallbackStillWorks:
    def test_thin_textile_still_applied_with_original_action(self, service):
        observation = AIObservation(
            product_name="薄款分趾袜", product_type="split_toe_socks", material="thin_knit",
            rigidity="soft", foldability="good", compressibility="good",
            length_cm=20, width_cm=10, height_cm=4, weight_g=30,
            weight_scope="packaged_weight", **no_hard_kwargs(),
        )
        result = service.estimate(observation)
        assert "AGR-THIN-TEXTILE-001" in result.applied_profile_ids
        # 原 smallest_axis_scale 参数：normal ×0.75、conservative ×0.9
        assert result.normal.height_cm == pytest.approx(3.0)
        assert result.conservative.height_cm == pytest.approx(3.6)
        assert result.conservative.height_cm >= result.normal.height_cm


class TestBadHistoricalSamplesExitRuntime:
    @pytest.mark.parametrize("rule_kwargs", [
        # CAL-029 unknown
        dict(product_type="coach_style_bag", material="pu_leather",
             rigidity="semi_rigid", requires_shape_retention=True),
        # CAL-054 after_actual（同时是旧 AGR-HARD-PROTRUSION-001 的污染 source）
        dict(product_type="car_ac_vent_aroma_diffuser_with_clip", material="aluminum_alloy_plastic_clip",
             rigidity="hard", requires_shape_retention=False),
        # CAL-057 after_actual
        dict(product_type="camera_wrist_strap_quick_release", material="nylon_webbing_metal_plastic_buckle",
             rigidity="semi_rigid", requires_shape_retention=False),
        # CAL-062 after_actual
        dict(product_type="anime_airpods_earphone_case", material="resin_hardshell_with_hook",
             rigidity="unknown", requires_shape_retention=None),
        # CAL-070 unknown
        dict(product_type="hair_weft_single_bundle", material="",
             rigidity="unknown", requires_shape_retention=None),
    ])
    def test_bad_sample_has_no_runtime_influence_path(self, service, rule_kwargs):
        sample_id = {
            "coach_style_bag": "CAL-029",
            "car_ac_vent_aroma_diffuser_with_clip": "CAL-054",
            "camera_wrist_strap_quick_release": "CAL-057",
            "anime_airpods_earphone_case": "CAL-062",
            "hair_weft_single_bundle": "CAL-070",
        }[rule_kwargs["product_type"]]
        observation = AIObservation(**rule_kwargs)
        result = service.estimate(observation)
        # 不能成为 numeric candidate / 不能进入 sample match
        assert result.candidate_records["cal_match_audit"]["sample_matches"] == []
        assert sample_id not in result.applied_profile_ids
        # 不能通过 sample rule 或已停用 aggregate 触发 structure risk
        risk_ids = result.candidate_records["cal_match_audit"]["structure_risk_rule_ids"]
        assert sample_id not in risk_ids

    def test_cal054_pollution_path_via_disabled_aggregate_is_closed(self, service):
        # 旧 AGR-HARD-PROTRUSION-001 的 match 条件（diffuser + hard/semi_rigid），
        # 且声称 shape retention（触发 structure risk 扫描）；
        # aggregate 已 disabled，CAL-054 不得再经此进入 risk 链。
        observation = AIObservation(
            product_type="car_ac_vent_aroma_diffuser_with_clip", material="aluminum_alloy_plastic_clip",
            rigidity="hard", requires_shape_retention=True,
            length_cm=12, width_cm=5, height_cm=4, weight_g=60,
        )
        result = service.estimate(observation)
        risk_ids = result.candidate_records["cal_match_audit"]["structure_risk_rule_ids"]
        assert "AGR-HARD-PROTRUSION-001" not in risk_ids
        assert "CAL-054" not in risk_ids
        assert "AGR-HARD-PROTRUSION-001" not in result.applied_profile_ids
