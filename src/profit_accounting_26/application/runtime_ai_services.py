from __future__ import annotations

from copy import copy
from dataclasses import dataclass, field, replace
from typing import Any

from profit_accounting_26.application.local_reestimate_service import (
    LocalReestimateResult,
    LocalReestimateService,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal


def apply_confirmed_facts(observation: AIObservation, confirmed_facts: dict[str, Any]) -> dict[str, Any]:
    """Apply user-confirmed facts onto an observation copy (user > page > AI).

    ``confirmed_facts`` entries are ``{"value": X, "source": "user_confirmed"}``
    or plain values.  Returns per-field conflicts; never mutates a raw AI
    observation because callers always pass a copy.
    """
    if not isinstance(confirmed_facts, dict):
        return {}
    conflicts: dict[str, Any] = {}
    for field, entry in confirmed_facts.items():
        if field not in observation.__dataclass_fields__:
            continue
        if isinstance(entry, dict) and "value" in entry:
            value = entry["value"]
        else:
            value = entry
        if value is None or value == "":
            continue
        ai_value = getattr(observation, field)
        if ai_value is not None and ai_value != value:
            conflicts[field] = {"user_confirmed": value, "ai_returned": ai_value}
        setattr(observation, field, value)
        if field == "product_name":
            observation.display_product_summary = str(value)
    if "weight_g" in confirmed_facts:
        observation.weight_scope = "net_weight"
    if any(field in confirmed_facts for field in ("length_cm", "width_cm", "height_cm")):
        observation.dimension_scope = "product_size"
    if conflicts:
        observation.raw_payload.setdefault("user_confirmed_conflicts", {}).update(conflicts)
    return conflicts


@dataclass(slots=True)
class RecognitionOutcome:
    """Minimal result contract of one recognition run.

    ``raw_observation`` / ``raw_ai_proposal`` are the pure external AI result,
    frozen before any local rule.  ``arbitration_observation`` is the copy with
    confirmed facts applied (user > page > AI); ``adopted_proposal`` is the
    final local-arbitrated proposal.  UI never reverse-reads service state.
    """

    raw_observation: AIObservation
    raw_ai_proposal: PackagingProposal | None
    adopted_proposal: PackagingProposal | None
    arbitration_observation: AIObservation
    arbitration_trace: dict[str, Any] = field(default_factory=dict)


class RuntimePackagingArbitrator:
    """Production packaging boundary for the simplified V1.2 AI contracts.

    The bundled baseline contains no calibration samples or numeric rules.  The
    runtime uses ``PackagingEstimationService`` for deterministic physical
    validation and generic safety fallback.  Only rules from an explicitly
    activated Formal Bundle that were recorded as validated rule IDs may
    participate in runtime arbitration.
    """

    SAFETY_CALIBRATION_VERSION = "runtime-safety-only-v1.2"

    def __init__(
        self,
        formal_service: PackagingEstimationService,
        calibration_manager: Any,
        *,
        safety_service: PackagingEstimationService | None = None,
    ) -> None:
        self.formal_service = formal_service
        self.calibration_manager = calibration_manager
        self.safety_service = safety_service or PackagingEstimationService(
            calibration_version=self.SAFETY_CALIBRATION_VERSION,
        )

    def _active_formal_package(self) -> dict[str, Any] | None:
        active = self.calibration_manager.active_package()
        if not isinstance(active, dict):
            return None
        metadata = active.get("metadata") if isinstance(active.get("metadata"), dict) else {}
        return active if metadata.get("formal_bundle") is True else None

    @staticmethod
    def _validated_rule_ids(package: dict[str, Any]) -> set[str]:
        metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
        return {
            str(rule_id)
            for rule_id in (metadata.get("validated_rule_ids") or [])
            if str(rule_id).strip()
        }

    def _formal_validated_service(self, package: dict[str, Any]) -> PackagingEstimationService | None:
        allowed = self._validated_rule_ids(package)
        if not allowed:
            return None

        # Work on a shallow service copy so runtime filtering never mutates the
        # CalibrationManager-bound service or its rollback/verification state.
        service = copy(self.formal_service)
        registry = dict(getattr(self.formal_service, "registry", {}) or {})
        registry["aggregate_rules"] = [
            rule
            for rule in (registry.get("aggregate_rules") or [])
            if isinstance(rule, dict) and str(rule.get("rule_id") or "") in allowed
        ]
        registry["sample_rules"] = [
            rule
            for rule in (registry.get("sample_rules") or [])
            if isinstance(rule, dict) and str(rule.get("rule_id") or "") in allowed
        ]
        service.registry = registry
        return service

    def estimate(
        self,
        observation: AIObservation,
        *,
        external_proposal: PackagingProposal | None,
    ) -> PackagingProposal:
        formal_package = self._active_formal_package()
        if formal_package is not None:
            formal_service = self._formal_validated_service(formal_package)
            if formal_service is not None:
                return formal_service.estimate(
                    observation,
                    external_proposal=external_proposal,
                )

        # Neutral builtin and invalid/unvalidated formal metadata are safety-only.
        return self.safety_service.estimate(
            observation,
            external_proposal=external_proposal,
        )


class RuntimeRecognitionService:
    """Run frozen visual recognition first, then deterministic local arbitration.

    Returns a single ``RecognitionOutcome``: the raw AI result is frozen before
    arbitration, and the UI never reads "the last result" back from the service.
    """

    def __init__(
        self,
        base_service: RecognitionService,
        packaging_arbitrator: RuntimePackagingArbitrator,
    ) -> None:
        self.base_service = base_service
        self.packaging_arbitrator = packaging_arbitrator

    def __getattr__(self, name: str):
        return getattr(self.base_service, name)

    def recognize(self, *args, **kwargs) -> RecognitionOutcome:
        user_context = kwargs.get("user_context") or {}
        if not isinstance(user_context, dict):
            user_context = {}
        # Accept the previous wrapper for callers still on the old contract.
        if set(user_context) == {"confirmed_facts"} and isinstance(user_context["confirmed_facts"], dict):
            user_context = dict(user_context["confirmed_facts"])

        raw_observation, raw_ai_proposal = self.base_service.recognize(*args, **kwargs)
        # 复制一份用于仲裁：raw_observation 保持原始值，永不被用户事实覆盖。
        arbitration_observation = copy(raw_observation)
        arbitration_observation.raw_payload = dict(raw_observation.raw_payload or {})
        conflicts = apply_confirmed_facts(arbitration_observation, user_context)
        adopted: PackagingProposal | None = None
        if raw_ai_proposal is not None:
            adopted = self.packaging_arbitrator.estimate(
                arbitration_observation,
                external_proposal=raw_ai_proposal,
            )
        return RecognitionOutcome(
            raw_observation=raw_observation,
            raw_ai_proposal=raw_ai_proposal,
            adopted_proposal=adopted,
            arbitration_observation=arbitration_observation,
            arbitration_trace={
                "confirmed_facts_applied": {
                    key: entry.get("value") if isinstance(entry, dict) else entry
                    for key, entry in user_context.items()
                    if key in arbitration_observation.__dataclass_fields__
                },
                "conflicts": conflicts,
            },
        )


class RuntimeLocalReestimateService:
    """Apply the same local safety boundary after text-only corrected re-estimate."""

    def __init__(
        self,
        base_service: LocalReestimateService,
        packaging_arbitrator: RuntimePackagingArbitrator,
    ) -> None:
        self.base_service = base_service
        self.packaging_arbitrator = packaging_arbitrator

    def __getattr__(self, name: str):
        return getattr(self.base_service, name)

    @staticmethod
    def _observation_from_context(context: dict[str, Any]) -> AIObservation:
        confirmed = context.get("confirmed_facts")
        confirmed = confirmed if isinstance(confirmed, dict) else {}
        observation = AIObservation(product_name=str(context.get("product_name") or "").strip())

        def confirmed_value(field: str):
            raw = confirmed.get(field)
            if isinstance(raw, dict):
                return raw.get("value")
            return raw

        for field in ("length_cm", "width_cm", "height_cm", "weight_g"):
            value = confirmed_value(field)
            if value is not None and value != "":
                setattr(observation, field, value)

        if any(
            getattr(observation, field) is not None
            for field in ("length_cm", "width_cm", "height_cm")
        ):
            observation.dimension_scope = "product_size"
            observation.dimension_value_source = "user_confirmed"
        if observation.weight_g is not None:
            observation.weight_scope = "net_weight"
            observation.weight_value_source = "user_confirmed"
        observation.raw_payload = {"confirmed_facts": confirmed}
        return observation

    def reestimate(self, **context: Any) -> LocalReestimateResult:
        result = self.base_service.reestimate(**context)
        proposal = result.packaging_proposal
        if proposal is None:
            return result

        observation = self._observation_from_context(context)
        arbitrated = self.packaging_arbitrator.estimate(
            observation,
            external_proposal=proposal,
        )
        scenario = arbitrated.conservative if arbitrated.conservative.is_complete() else None
        return replace(
            result,
            shipment=scenario,
            packaging_proposal=arbitrated,
            # 保留文字 AI 原始提案，与仲裁后 adopted 可区分
            reestimate_raw_proposal=proposal,
            arbitration_trace={
                "confirmed_facts_applied": {
                    key: (entry.get("value") if isinstance(entry, dict) else entry)
                    for key, entry in (context.get("confirmed_facts") or {}).items()
                    if key in observation.__dataclass_fields__
                },
                "source": "local_reestimate_arbitration",
            },
        )
