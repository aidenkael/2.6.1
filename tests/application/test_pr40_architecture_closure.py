"""PR #40 架构收口 targeted tests（对应任务书第十五节 17 项）。

覆盖：
1. 用户裸重700g → AI raw 650g：ai_initial 保存 650g，本地仲裁使用 700g 硬事实
2. 左卡永远显示 raw AI
3. 右卡显示 adopted
4. 完整 AI shipment 未触发正式规则时不被 generic 覆盖
5. structure 非法值不能触发规则
6. quantity 未知按 1 单位估算时不能保存为真实数量 1
7. Direct Calibration 仍得到纯 AI baseline
8. 重估包含首次 AI 最小 structure/evidence
9. 重估 raw 与 adopted 可区分
10. ai_initial 历史编辑永不覆盖
11. manifest 能明确区分 AI/local/user/actual
12. Candidate 规则不能进入 Runtime
13. 只有 validated 规则可以参与 Runtime
14. 物流只读取右卡
15. quantity_summary 不参与物流算法
16. 旧历史兼容读取
17. 当前 3.0.1 版本不变

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import json
import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from profit_accounting_26.application.calibration_export_service import (  # noqa: E402
    _ai_initial_block,
    _machine_ai_initial,
    _machine_local_adopted,
    _machine_user_feedback,
)
from profit_accounting_26.application.calculation_session import CalculationSession  # noqa: E402
from profit_accounting_26.application.data_contracts import (  # noqa: E402
    attach_v2_block,
    record_from_payload,
    v2_block_from_payload,
)
from profit_accounting_26.application.local_reestimate_service import (  # noqa: E402
    LocalReestimateResult,
    LocalReestimateService,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService  # noqa: E402
from profit_accounting_26.application.recognition_service import RecognitionService  # noqa: E402
from profit_accounting_26.application.runtime_ai_services import (  # noqa: E402
    RecognitionOutcome,
    RuntimePackagingArbitrator,
    RuntimeRecognitionService,
    apply_confirmed_facts,
)
from profit_accounting_26.domain.models import (  # noqa: E402
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)


# ------------------------------------------------------------------ helpers


def _proposal(source: str = "raw", *, length: float = 30.0, width: float = 20.0,
              height: float = 10.0, weight: float = 500.0) -> PackagingProposal:
    normal = PackagingScenario(
        label="AI估算", packaging_method="袋装发货", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        confidence="medium", needs_review=False,
    )
    conservative = PackagingScenario(
        label="当前采用", packaging_method="袋装发货", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        confidence="medium", needs_review=False,
    )
    return PackagingProposal(normal=normal, conservative=conservative, proposal_source=source)


class _Manager:
    def __init__(self, package=None):
        self.package = package

    def active_package(self):
        return self.package


class _FakeRecognitionService:
    PROMPT_VERSION = "frozen-test"

    def __init__(self, observation, proposal):
        self.observation = observation
        self.proposal = proposal

    def recognize(self, *args, **kwargs):
        del args, kwargs
        return self.observation, self.proposal


class _FakePackagingService:
    def __init__(self, name: str, registry=None):
        self.name = name
        self.registry = registry or {"aggregate_rules": [], "sample_rules": []}
        self.calibration_version = name

    def estimate(self, observation, *, external_proposal):
        del observation
        ids = [
            str(rule.get("rule_id"))
            for key in ("aggregate_rules", "sample_rules")
            for rule in self.registry.get(key, [])
            if isinstance(rule, dict) and rule.get("enabled", True)
        ]
        return replace(
            external_proposal,
            proposal_source=self.name,
            applied_profile_ids=ids,
            calibration_version=self.calibration_version,
        )


# ==================================================================
# 1. 用户裸重700g → AI raw 650g：ai_initial 保存 650g，仲裁使用 700g
# ==================================================================


def test_user_weight_700_ai_raw_650_ai_initial_keeps_raw_and_arbitration_uses_700():
    raw_observation = AIObservation(product_name="bag", weight_g=650.0, weight_scope="unknown")
    raw_proposal = _proposal("vision_ai_v1", weight=650.0)

    class _CapturingSafety(_FakePackagingService):
        def __init__(self):
            super().__init__("safety")
            self.observation = None

        def estimate(self, observation, *, external_proposal):
            self.observation = observation
            return super().estimate(observation, external_proposal=external_proposal)

    safety = _CapturingSafety()
    runtime = RuntimeRecognitionService(
        _FakeRecognitionService(raw_observation, raw_proposal),
        RuntimePackagingArbitrator(
            _FakePackagingService("formal"),
            _Manager({"metadata": {"builtin": True}}),
            safety_service=safety,
        ),
    )
    outcome = runtime.recognize(
        [], user_context={"confirmed_facts": {"weight_g": {"value": 700.0, "source": "user_confirmed"}}},
    )

    # raw AI 永久保留 650g
    assert outcome.raw_observation.weight_g == 650.0
    # 仲裁副本使用 700g 硬事实
    assert safety.observation.weight_g == 700.0
    assert safety.observation.weight_scope == "net_weight"
    assert outcome.arbitration_trace["conflicts"]["weight_g"]["user_confirmed"] == 700.0
    assert outcome.arbitration_trace["conflicts"]["weight_g"]["ai_returned"] == 650.0


def test_apply_confirmed_facts_does_not_mutate_raw():
    raw = AIObservation(weight_g=650.0)
    copied = AIObservation.from_dict(raw.to_dict())
    conflicts = apply_confirmed_facts(copied, {"weight_g": {"value": 700.0, "source": "user_confirmed"}})
    assert raw.weight_g == 650.0
    assert copied.weight_g == 700.0
    assert conflicts["weight_g"]["user_confirmed"] == 700.0


# ==================================================================
# 2. 左卡永远显示 raw AI；3. 右卡显示 adopted
# ==================================================================


def test_outcome_separates_raw_ai_from_adopted():
    raw = _proposal("vision_ai_v1", weight=500.0)
    adopted = _proposal("safety", weight=620.0)
    outcome = RecognitionOutcome(
        raw_observation=AIObservation(product_name="bag"),
        raw_ai_proposal=raw,
        adopted_proposal=adopted,
        arbitration_observation=AIObservation(product_name="bag"),
        arbitration_trace={},
    )
    # 左卡 = raw AI（只读、永不覆盖）；右卡 = adopted（物流唯一输入）
    assert outcome.raw_ai_proposal.normal.weight_g == 500.0
    assert outcome.adopted_proposal.normal.weight_g == 620.0
    assert outcome.raw_ai_proposal is not outcome.adopted_proposal


def test_calculation_session_stores_raw_and_adopted_separately():
    session = CalculationSession()
    raw = _proposal("vision_ai_v1", weight=500.0)
    adopted = _proposal("safety", weight=620.0)
    session.ai_packaging_proposal = raw
    session.adopt(adopted)
    assert session.ai_packaging_proposal.proposal_source == "vision_ai_v1"
    assert session.adopted_packaging.proposal_source == "safety"
    assert session.ai_packaging_proposal.normal.weight_g == 500.0
    assert session.adopted_packaging.normal.weight_g == 620.0


# ==================================================================
# 4. 完整 AI shipment 未触发正式规则时不被 generic 覆盖
# ==================================================================


def test_complete_ai_shipment_not_overridden_by_generic_without_validated_rules():
    service = PackagingEstimationService(calibration_version="safety-test")
    observation = AIObservation(product_name="袋装商品", rigidity="soft")
    proposal = service.estimate(observation, external_proposal=_proposal("vision_ai_v1"))
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.weight_g == 500.0
    assert proposal.normal.length_cm == 30.0
    assert "GENERIC" not in proposal.applied_profile_ids


def test_soft_semantic_conflict_records_warning_keeps_ai_shipment():
    """AI shipment 完整但 structure 词不够理想：warning + needs_review，不换成 generic。"""
    service = PackagingEstimationService(calibration_version="safety-test")
    observation = AIObservation(
        product_name="柔性商品", compressibility="limited",
        length_cm=20, width_cm=15, height_cm=6, weight_g=100,
        weight_scope="net_weight", dimension_scope="product_size",
    )
    normal = PackagingScenario(
        label="AI估算", packaging_method="袋装", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=22.0, width_cm=17.0, height_cm=8.0, weight_g=130.0, confidence="medium",
    )
    conservative = PackagingScenario(
        label="当前采用", packaging_method="袋装", packaging_state=PackagingState.MODERATE_COMPRESSION,
        length_cm=24.0, width_cm=19.0, height_cm=10.0, weight_g=150.0, confidence="medium",
    )
    proposal = service.estimate(
        observation,
        external_proposal=PackagingProposal(normal=normal, conservative=conservative, proposal_source="vision_ai_v1"),
    )
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.length_cm == 22.0
    assert proposal.normal.weight_g == 130.0
    assert "declared_transport_adjustment_not_reflected" in proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert proposal.normal.needs_review is True


# ==================================================================
# 5. structure 非法值不能触发规则
# ==================================================================


def test_illegal_structure_values_cannot_trigger_rules():
    payload = {
        "product_name": "测试",
        "observed": {"product_price_rmb": None, "page_shipping_rmb": None,
                     "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                     "bare_weight_g": None},
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 20, "width_cm": 10, "height_cm": 5, "weight_g": 100, "state": "袋装"},
        "structure": {"rigidity": "super_hard", "foldability": "extreme", "compressibility": "maximum",
                      "packing_actions": ["evil_action"]},
        "note": "",
    }
    obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
    assert obs.rigidity == "unknown"
    assert obs.foldability == "unknown"
    assert obs.compressibility == "unknown"
    assert obs.packing_actions == []


# ==================================================================
# 6. quantity 未知按 1 单位估算时不能保存为真实数量 1
# ==================================================================


def test_unknown_quantity_is_marked_assumed_not_real_1():
    payload = {
        "product_name": "测试",
        "observed": {"product_price_rmb": None, "page_shipping_rmb": None,
                     "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                     "bare_weight_g": None},
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 20, "width_cm": 10, "height_cm": 5, "weight_g": 100, "state": "袋装"},
        "quantity": {"purchase_quantity": None, "quantity_source": None, "quantity_summary": "无法确认"},
        "note": "",
    }
    obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
    assert obs.quantity == 1  # shipment 按 1 个销售单位估算
    assert obs.quantity_source == "assumed/unknown"  # 明确标记，不伪装成真实数量 1
    assert obs.quantity_summary == "无法确认"


def test_confirmed_quantity_keeps_source():
    payload = {
        "product_name": "测试",
        "observed": {"product_price_rmb": None, "page_shipping_rmb": None,
                     "bare_dimensions_cm": {"length": None, "width": None, "height": None},
                     "bare_weight_g": None},
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 20, "width_cm": 10, "height_cm": 5, "weight_g": 100, "state": "袋装"},
        "quantity": {"purchase_quantity": 3, "quantity_source": "detail_page", "quantity_summary": "3单位"},
        "note": "",
    }
    obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
    assert obs.quantity == 3
    assert obs.quantity_source == "detail_page"


# ==================================================================
# 7. Direct Calibration 仍得到纯 AI baseline
# ==================================================================


def test_base_recognition_service_returns_pure_ai_without_arbitration():
    """Direct Calibration 调用基础 RecognitionService：不做本地规则，proposal_source 保持 vision_ai_v1。"""
    payload = {
        "product_name": "纯AI商品",
        "observed": {"product_price_rmb": 10.0, "page_shipping_rmb": 5.0,
                     "bare_dimensions_cm": {"length": 20, "width": 10, "height": 5},
                     "bare_weight_g": 100},
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 22, "width_cm": 12, "height_cm": 6, "weight_g": 120, "state": "袋装"},
        "note": "",
    }
    response = {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}
    observation, proposal = RecognitionService.parse_payload(response, model="vision-test")
    assert proposal is not None
    assert proposal.proposal_source == "vision_ai_v1"
    assert proposal.applied_profile_ids == []
    assert proposal.engine_version == "vision-runtime-v1"


# ==================================================================
# 8. 重估包含首次 AI 最小 structure/evidence
# ==================================================================


def test_reestimate_context_includes_first_ai_minimal_structure_and_evidence():
    initial_obs = {
        "product_name": "真实商品名",
        "rigidity": "soft",
        "foldability": "good",
        "compressibility": "good",
        "requires_shape_retention": True,
        "packing_actions": ["flat_fold"],
        "has_hard_bottom": True,
    }
    initial_raw = {
        "observed": {"product_price_rmb": 59.9},
        "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500, "state": "袋装"},
        "field_evidence": {"has_hard_bottom": {"source_image_index": 1, "raw_text": "底部硬板"}},
    }
    prompt = LocalReestimateService._context(
        product_name="真实商品名",
        confirmed_facts={"weight_g": 500},
        current_shipment={"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500},
        user_correction="更大",
        initial_ai_observation=initial_obs,
        initial_ai_raw_payload=initial_raw,
    )
    assert "initial_ai_context" in prompt
    assert "rigidity" in prompt
    assert "foldability" in prompt
    assert "requires_shape_retention" in prompt
    assert "initial_field_evidence" in prompt
    assert "has_hard_bottom" in prompt


# ==================================================================
# 9. 重估 raw 与 adopted 可区分
# ==================================================================


def test_reestimate_result_distinguishes_raw_from_adopted():
    raw = _proposal("corrected_reestimate_v1", weight=480.0)
    adopted = _proposal("safety", weight=520.0)
    result = LocalReestimateResult(
        shipment=adopted.conservative,
        packaging_proposal=adopted,
        reestimate_raw_proposal=raw,
        arbitration_trace={"source": "local_reestimate_arbitration"},
    )
    assert result.reestimate_raw_proposal.proposal_source == "corrected_reestimate_v1"
    assert result.reestimate_raw_proposal.normal.weight_g == 480.0
    assert result.packaging_proposal.proposal_source == "safety"
    assert result.packaging_proposal.normal.weight_g == 520.0
    assert result.arbitration_trace is not None


# ==================================================================
# 10. ai_initial 历史编辑永不覆盖
# ==================================================================


def test_v2_ai_initial_never_overwritten_on_update():
    payload: dict = {}
    attach_v2_block(payload, origin="new_calculation", revision=1,
                    ai_initial={"observation": {"weight_g": 650.0}}, current_estimate={})
    attach_v2_block(payload, origin="history_edit", revision=2,
                    ai_initial=None, current_estimate={"weight_g": 700.0})
    block = v2_block_from_payload(payload)
    assert block["ai_initial"]["observation"]["weight_g"] == 650.0
    assert block["current_estimate"]["weight_g"] == 700.0
    assert block["revision"] == 2


# ==================================================================
# 11. manifest 能明确区分 AI/local/user/actual
# ==================================================================


def test_manifest_layers_distinguish_ai_local_user_actual():
    initial = {
        "provider": "openai",
        "model": "gpt-4o",
        "prompt_version": "2.6.1-visual-v1.8",
        "observation": {"product_name": "测试商品", "length_cm": 25, "weight_g": 600},
        "external_ai_packaging_proposal": _proposal("vision_ai_v1", weight=650.0).to_dict(),
        "adopted_packaging": _proposal("ai_candidate", weight=720.0).to_dict(),
    }
    ai_initial = _machine_ai_initial({"_v2": {"ai_initial": initial}})
    assert ai_initial is not None
    assert ai_initial["packaging_proposal"]["source_kind"] == "external_ai_packaging_proposal"

    local = _machine_local_adopted(initial)
    assert local is not None
    assert local["shipment"]["weight_g"] == 720.0
    assert local["proposal_source"] == "ai_candidate"

    # user_feedback 与 actual_logistics 分层
    assert set(_machine_user_feedback(None) or {}) <= {
        "feedback_id", "feedback_schema_version", "source", "created_at", "updated_at",
        "structure", "suggested_package", "actual_logistics", "user_note",
    }


# ==================================================================
# 12. Candidate 规则不能进入 Runtime；13. 只有 validated 规则可以参与
# ==================================================================


def _formal_package(validated_ids: list[str]) -> dict:
    return {"metadata": {"formal_bundle": True, "validated_rule_ids": validated_ids}}


def test_candidate_rule_never_enters_runtime():
    """candidate 规则（未列入 validated_rule_ids）不得参与 Runtime。"""
    formal = _FakePackagingService(
        "formal",
        registry={
            "aggregate_rules": [{"rule_id": "CANDIDATE-X", "enabled": True}],
            "sample_rules": [],
        },
    )
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager(_formal_package(validated_ids=["VALIDATED-1"])),
        safety_service=_FakePackagingService("safety"),
    )
    result = arbiter.estimate(AIObservation(product_name="item"), external_proposal=_proposal())
    # CANDIDATE-X 不在 validated_rule_ids → 规则被过滤，不参与 Runtime
    assert result.applied_profile_ids == []
    assert "CANDIDATE-X" not in result.applied_profile_ids


def test_only_validated_rules_participate_in_runtime():
    formal = _FakePackagingService(
        "formal",
        registry={
            "aggregate_rules": [
                {"rule_id": "VALIDATED-1", "enabled": True},
                {"rule_id": "CANDIDATE-X", "enabled": True},
            ],
            "sample_rules": [],
        },
    )
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager(_formal_package(validated_ids=["VALIDATED-1"])),
        safety_service=_FakePackagingService("safety"),
    )
    result = arbiter.estimate(AIObservation(product_name="item"), external_proposal=_proposal())
    assert result.applied_profile_ids == ["VALIDATED-1"]
    assert "CANDIDATE-X" not in result.applied_profile_ids


# ==================================================================
# 14. 物流只读取右卡（adopted）
# ==================================================================


def test_logistics_only_reads_adopted_right_card():
    session = CalculationSession()
    raw = _proposal("vision_ai_v1", weight=500.0)
    adopted = _proposal("ai_candidate", weight=760.0)
    session.ai_packaging_proposal = raw
    session.adopt(adopted)
    # 物流只使用 adopted（右卡）的 conservative 数值
    logistics_weight = session.adopted_packaging.conservative.weight_g
    assert logistics_weight == 760.0
    assert session.adopted_packaging.conservative.weight_g != raw.normal.weight_g


# ==================================================================
# 15. quantity_summary 不参与物流算法
# ==================================================================


def test_quantity_summary_not_used_in_logistics_calculation():
    import pathlib

    from profit_accounting_26.application import packaging_estimation_service as pes
    from profit_accounting_26.engines.logistics import core as logistics_core

    assert "quantity_summary" not in pathlib.Path(pes.__file__).read_text(encoding="utf-8")
    assert "quantity_summary" not in pathlib.Path(logistics_core.__file__).read_text(encoding="utf-8")


# ==================================================================
# 16. 旧历史兼容读取
# ==================================================================


def test_legacy_record_without_v2_reads_compatibly():
    legacy = {
        "id": "legacy-1",
        "product_name": "旧商品",
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "normal": {"length_cm": 30, "weight_g": 500},
                "conservative": {"length_cm": 32, "weight_g": 550},
            },
        },
    }
    record = record_from_payload(legacy)
    assert record.record_id == "legacy-1"
    assert record.record_schema_version == "2.6.1"
    # 无 layers.ai_raw 的旧记录：ai_initial 保持 None，不伪造第一次 AI 数据
    assert record.ai_initial is None
    assert record.current_estimate["length_cm"] == 32


def test_legacy_record_with_ai_raw_reads_legacy_layers_marker():
    legacy = {
        "id": "legacy-2",
        "product_name": "旧商品",
        "layers": {
            "ai_raw": {"observation": {"product_name": "旧商品", "weight_g": 500}},
            "adopted": {"selected_packaging": "正常档", "normal": {"length_cm": 30, "weight_g": 500}},
        },
    }
    record = record_from_payload(legacy)
    assert record.record_schema_version == "2.6.1"
    assert record.ai_initial is not None
    assert "legacy_layers_ai_raw" in record.ai_initial


# ==================================================================
# 17. 当前 3.0.1 版本不变
# ==================================================================


def test_app_title_keeps_3_0_1():
    import pathlib

    app_src = pathlib.Path("src/profit_accounting_26/ui/app.py").read_text(encoding="utf-8")
    assert "UU护航 3.0.1" in app_src


def test_no_real_network_in_tests():
    """禁止真实 API / 浏览器 / 外部链接：纯逻辑测试文件不得发起网络请求。"""
    assert not any(token in __file__ for token in ("requests", "playwright", "selenium"))
