"""Baseline vs experiment strategy support (test-side only).

The harness must be able to compare the current production rules
(``baseline``) against future experimental rules without ever touching
production code. Experiments are implemented by SUBCLASSING
``PackagingEstimationService`` inside this module and copying the baseline
instance state, so:

* production ``src/`` code is never modified or monkeypatched globally;
* this module lives under ``tests/`` and is never imported by production;
* every experiment declares which evaluation data it needs before its result
  is meaningful.

Only the ``baseline`` strategy represents production behavior. All other
strategies are hypotheses from the previous audit and MUST NOT be used to
claim accuracy improvements until real cases exist.
"""

from __future__ import annotations

from typing import Any

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation, PackagingScenario


class ExperimentStrategy:
    """Base strategy. ``build_service`` returns the service used for FINAL."""

    experiment_id = "baseline"
    name = "当前生产基线"
    description = "PackagingEstimationService 原样运行（生产规则）。"
    is_production_baseline = True
    data_requirements: list[str] = []

    def build_service(self, baseline_service: PackagingEstimationService) -> PackagingEstimationService:
        return baseline_service


def _clone_as(baseline_service: PackagingEstimationService, cls: type) -> PackagingEstimationService:
    """Give an existing configured service instance a subclass identity."""
    instance = cls.__new__(cls)
    instance.__dict__.update(baseline_service.__dict__)
    return instance


class _RelaxedOutlineValidationService(PackagingEstimationService):
    def _validate_candidate(self, normal: PackagingScenario, conservative: PackagingScenario,
                            observation: AIObservation) -> list[str]:
        reasons = super()._validate_candidate(normal, conservative, observation)
        return [reason for reason in reasons if reason != "packing_action_not_reflected_in_outline"]


class ExperimentARelaxedOutlineCheck(ExperimentStrategy):
    """审计假设 A：放宽 packing_action_not_reflected_in_outline。

    已扁平/已收纳商品的包装外廓不小于商品展开外廓最长边时，当前基线会否决
    AI 候选。该实验仅移除此否决理由，其余校验保持不变。
    """

    experiment_id = "expA_relaxed_outline_check"
    name = "实验A：放宽 packing_action_not_reflected_in_outline"
    description = "移除 packing_action_not_reflected_in_outline 否决理由，其余规则不变。"
    is_production_baseline = False
    data_requirements = [
        "真实案例：声明 flat_fold/roll/coil/compress 且 AI 候选被该理由否决",
        "人工标准：normal_packaging 尺寸区间（用于比较基线与实验的最终准确率）",
    ]

    def build_service(self, baseline_service: PackagingEstimationService) -> PackagingEstimationService:
        return _clone_as(baseline_service, _RelaxedOutlineValidationService)


class _IndependentPackagingCandidateService(PackagingEstimationService):
    def _validate_ai_semantics(self, normal: PackagingScenario, conservative: PackagingScenario,
                               observation: AIObservation,
                               *, semantic_observation: AIObservation | None = None) -> list[str]:
        reasons = super()._validate_ai_semantics(
            normal, conservative, observation, semantic_observation=semantic_observation,
        )
        # dimension 语义问题只影响 observation 层尺寸，不再株连 AI 独立给出的包装候选
        return [reason for reason in reasons if reason != "dimension_evidence_not_outer_dimensions"]


class ExperimentBIndependentPackagingCandidate(ExperimentStrategy):
    """审计假设 B：dimension 语义问题不株连独立包装候选。

    当前基线把 observation 层的 dimension_semantic_issue 作为否决 AI 包装候选
    的理由。该实验移除此株连；observation 层尺寸仍然被 parser 清空。
    """

    experiment_id = "expB_independent_packaging_candidate"
    name = "实验B：dimension 语义问题不株连包装候选"
    description = "移除 dimension_evidence_not_outer_dimensions 对 AI 包装候选的否决。"
    is_production_baseline = False
    data_requirements = [
        "真实案例：raw response 的 field_evidence.dimensions 含范围/部件语义且 AI 同时给出完整包装候选",
        "人工标准：normal_packaging 尺寸区间与 acceptable_methods",
        "图片角色标注（image_role=dimension）以便未来比较带角色 prompt",
    ]

    def build_service(self, baseline_service: PackagingEstimationService) -> PackagingEstimationService:
        return _clone_as(baseline_service, _IndependentPackagingCandidateService)


class _CalRiskOnlyForCompleteAIService(PackagingEstimationService):
    def _coordinate_ai_cal_fields(self, ai_normal, ai_conservative, cal_normal, cal_conservative,
                                  *, match_strength: str, observation: AIObservation):
        if (ai_normal and ai_conservative and ai_normal.is_complete() and ai_conservative.is_complete()):
            trace: dict[str, Any] = {"match_strength": match_strength, "adjusted_fields": {}, "risk_only": True}
            return ai_normal, ai_conservative, trace
        return super()._coordinate_ai_cal_fields(
            ai_normal, ai_conservative, cal_normal, cal_conservative,
            match_strength=match_strength, observation=observation,
        )


class ExperimentCCalRiskOnly(ExperimentStrategy):
    """审计假设 C：AI 完整候选时 CAL 只提示风险、不改数值。

    当前基线在 strong 匹配且 AI 非 high 置信时会用 CAL 参考值逐字段覆盖。
    该实验在 AI normal+conservative 候选完整时强制 risk-only。
    """

    experiment_id = "expC_cal_risk_only_for_complete_ai"
    name = "实验C：AI 完整候选时 CAL risk-only"
    description = "AI 候选完整时禁止 CAL 字段级覆盖，仅保留风险提示。"
    is_production_baseline = False
    data_requirements = [
        "真实案例：cal_coordination.adjusted_fields 非空（CAL 实际改写了 AI 值）",
        "人工标准：normal_packaging 尺寸区间，用于判断 AI 原值与 CAL 覆盖值谁更准",
    ]

    def build_service(self, baseline_service: PackagingEstimationService) -> PackagingEstimationService:
        return _clone_as(baseline_service, _CalRiskOnlyForCompleteAIService)


EXPERIMENTS: dict[str, ExperimentStrategy] = {
    strategy.experiment_id: strategy
    for strategy in (
        ExperimentStrategy(),
        ExperimentARelaxedOutlineCheck(),
        ExperimentBIndependentPackagingCandidate(),
        ExperimentCCalRiskOnly(),
    )
}


def get_strategy(experiment_id: str) -> ExperimentStrategy:
    try:
        return EXPERIMENTS[experiment_id]
    except KeyError:
        known = ", ".join(sorted(EXPERIMENTS))
        raise ValueError(f"未知实验: {experiment_id}（可用: {known}）") from None
