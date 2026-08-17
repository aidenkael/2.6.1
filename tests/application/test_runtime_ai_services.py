from __future__ import annotations

from dataclasses import replace

from profit_accounting_26.application.local_reestimate_service import LocalReestimateResult
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.runtime_ai_services import (
    RuntimeLocalReestimateService,
    RuntimePackagingArbitrator,
    RuntimeRecognitionService,
)
from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
)


def _proposal(source: str = "raw", *, weight: float = 300.0) -> PackagingProposal:
    normal = PackagingScenario(
        label="AI估算",
        packaging_method="袋装发货",
        length_cm=20.0,
        width_cm=10.0,
        height_cm=5.0,
        weight_g=weight,
        confidence="medium",
    )
    conservative = PackagingScenario(
        label="当前采用",
        packaging_method="袋装发货",
        length_cm=20.0,
        width_cm=10.0,
        height_cm=5.0,
        weight_g=weight,
        confidence="medium",
    )
    return PackagingProposal(normal=normal, conservative=conservative, proposal_source=source)


class _Manager:
    def __init__(self, package=None):
        self.package = package

    def active_package(self):
        return self.package


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


class _FakeRecognitionService:
    PROMPT_VERSION = "frozen-test"

    def __init__(self, observation, proposal):
        self.observation = observation
        self.proposal = proposal

    def recognize(self, *args, **kwargs):
        del args, kwargs
        return self.observation, self.proposal


class _FakeReestimateService:
    PROMPT_VERSION = "frozen-reestimate-test"

    def __init__(self, result):
        self.result = result

    def reestimate(self, **context):
        del context
        return self.result


def test_legacy_or_builtin_runtime_uses_safety_only_service():
    formal = _FakePackagingService(
        "formal",
        registry={
            "aggregate_rules": [{"rule_id": "LEGACY-77", "enabled": True}],
            "sample_rules": [],
        },
    )
    safety = _FakePackagingService("safety")
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager({"metadata": {"builtin": True}}),
        safety_service=safety,
    )

    result = arbiter.estimate(AIObservation(product_name="socks"), external_proposal=_proposal())

    assert result.proposal_source == "safety"
    assert result.applied_profile_ids == []


def test_formal_runtime_filters_registry_to_validated_rule_ids_only():
    formal = _FakePackagingService(
        "formal",
        registry={
            "aggregate_rules": [
                {"rule_id": "LEGACY-77", "enabled": True},
                {"rule_id": "FORMAL-NEW-1", "enabled": True},
            ],
            "sample_rules": [
                {"rule_id": "FORMAL-NEW-2", "enabled": True},
                {"rule_id": "LEGACY-SAMPLE", "enabled": True},
            ],
        },
    )
    package = {
        "metadata": {
            "formal_bundle": True,
            "validated_rule_ids": ["FORMAL-NEW-1", "FORMAL-NEW-2"],
        }
    }
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager(package),
        safety_service=_FakePackagingService("safety"),
    )

    result = arbiter.estimate(AIObservation(product_name="item"), external_proposal=_proposal())

    assert result.proposal_source == "formal"
    assert result.applied_profile_ids == ["FORMAL-NEW-1", "FORMAL-NEW-2"]
    # Filtering works on a service copy; CalibrationManager-bound state is untouched.
    assert [rule["rule_id"] for rule in formal.registry["aggregate_rules"]] == [
        "LEGACY-77",
        "FORMAL-NEW-1",
    ]


def test_formal_bundle_without_validated_ids_falls_back_to_safety_only():
    formal = _FakePackagingService("formal")
    package = {"metadata": {"formal_bundle": True, "validated_rule_ids": []}}
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager(package),
        safety_service=_FakePackagingService("safety"),
    )

    result = arbiter.estimate(AIObservation(), external_proposal=_proposal())

    assert result.proposal_source == "safety"


def test_real_safety_service_preserves_valid_ai_candidate_without_cal_rules():
    formal = PackagingEstimationService(calibration_version="legacy-test")
    formal.registry = {
        "aggregate_rules": [
            {
                "rule_id": "LEGACY-77",
                "enabled": True,
                "priority": 100,
                "name": "legacy should not run",
                "match": {"any_terms": ["socks"]},
                "action": {
                    "type": "smallest_axis_scale",
                    "normal": 0.5,
                    "conservative": 0.6,
                },
            }
        ],
        "sample_rules": [],
    }
    arbiter = RuntimePackagingArbitrator(
        formal,
        _Manager({"metadata": {"builtin": True}}),
    )

    result = arbiter.estimate(
        AIObservation(product_name="thin socks"),
        external_proposal=_proposal(),
    )

    assert result.normal.length_cm == 20.0
    assert result.normal.width_cm == 10.0
    assert result.normal.height_cm == 5.0
    assert result.normal.weight_g == 300.0
    assert result.applied_profile_ids == []
    assert result.calibration_version == RuntimePackagingArbitrator.SAFETY_CALIBRATION_VERSION


def test_runtime_recognition_keeps_frozen_ai_then_applies_local_arbitration():
    observation = AIObservation(product_name="bag")
    raw = _proposal("raw")
    base = _FakeRecognitionService(observation, raw)
    arbiter = RuntimePackagingArbitrator(
        _FakePackagingService("formal"),
        _Manager({"metadata": {"builtin": True}}),
        safety_service=_FakePackagingService("safety"),
    )
    runtime = RuntimeRecognitionService(base, arbiter)

    outcome = runtime.recognize([])

    # RecognitionOutcome 契约：raw AI 冻结 + adopted 仲裁结果分离
    assert outcome.raw_observation is observation
    assert outcome.raw_ai_proposal is raw
    assert outcome.adopted_proposal.proposal_source == "safety"
    assert outcome.arbitration_observation is not observation
    assert runtime.PROMPT_VERSION == "frozen-test"


def test_runtime_recognition_applies_confirmed_facts_before_arbitration():
    """用户确认裸重 700g、AI raw 650g：raw 保留 650g，仲裁使用 700g 硬事实。"""
    observation = AIObservation(product_name="bag", weight_g=650.0, weight_scope="unknown")
    raw = _proposal("raw", weight=650.0)

    class _CapturingSafety(_FakePackagingService):
        def __init__(self):
            super().__init__("safety")
            self.observation = None

        def estimate(self, observation, *, external_proposal):
            self.observation = observation
            return super().estimate(observation, external_proposal=external_proposal)

    safety = _CapturingSafety()
    base = _FakeRecognitionService(observation, raw)
    arbiter = RuntimePackagingArbitrator(
        _FakePackagingService("formal"),
        _Manager({"metadata": {"builtin": True}}),
        safety_service=safety,
    )
    runtime = RuntimeRecognitionService(base, arbiter)

    outcome = runtime.recognize(
        [],
        user_context={"confirmed_facts": {"weight_g": {"value": 700.0, "source": "user_confirmed"}}},
    )

    # raw AI 永久保留 650g
    assert outcome.raw_observation.weight_g == 650.0
    # 仲裁副本已应用 700g 硬事实
    assert safety.observation.weight_g == 700.0
    assert safety.observation.weight_scope == "net_weight"
    assert outcome.arbitration_trace["conflicts"]["weight_g"] == {
        "user_confirmed": 700.0, "ai_returned": 650.0,
    }


def test_runtime_local_reestimate_applies_safety_and_preserves_confirmed_facts():
    raw = _proposal("raw", weight=250.0)
    base_result = LocalReestimateResult(
        shipment=raw.normal,
        packaging_proposal=raw,
    )
    base = _FakeReestimateService(base_result)

    class _CapturingSafety(_FakePackagingService):
        def __init__(self):
            super().__init__("safety")
            self.observation = None

        def estimate(self, observation, *, external_proposal):
            self.observation = observation
            return super().estimate(observation, external_proposal=external_proposal)

    safety = _CapturingSafety()
    arbiter = RuntimePackagingArbitrator(
        _FakePackagingService("formal"),
        _Manager({"metadata": {"builtin": True}}),
        safety_service=safety,
    )
    runtime = RuntimeLocalReestimateService(base, arbiter)

    result = runtime.reestimate(
        product_name="soft bag",
        confirmed_facts={
            "weight_g": {"value": 200.0, "source": "user_confirmed"},
            "length_cm": {"value": 18.0, "source": "user_confirmed"},
        },
        current_shipment={},
        user_correction="袋装发货",
    )

    assert result.packaging_proposal.proposal_source == "safety"
    assert result.shipment is result.packaging_proposal.conservative
    assert safety.observation.product_name == "soft bag"
    assert safety.observation.weight_g == 200.0
    assert safety.observation.weight_scope == "net_weight"
    assert safety.observation.length_cm == 18.0
    assert safety.observation.dimension_scope == "product_size"
    assert runtime.PROMPT_VERSION == "frozen-reestimate-test"
