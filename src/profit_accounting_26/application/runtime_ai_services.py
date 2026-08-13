from __future__ import annotations

from copy import copy
from dataclasses import replace
from typing import Any

from profit_accounting_26.application.local_reestimate_service import (
    LocalReestimateResult,
    LocalReestimateService,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal


class RuntimePackagingArbitrator:
    """Production packaging boundary for the simplified V1.2 AI contracts.

    Legacy/builtin CAL assets stay available for audit and offline calibration, but
    they do not participate in production numeric overrides.  The runtime still
    uses ``PackagingEstimationService`` for deterministic physical validation and
    generic safety fallback.  Only rules from an explicitly activated Formal
    Bundle that were recorded as validated rule IDs may participate in runtime
    arbitration.
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

        # Builtin/legacy packages and malformed formal metadata are deliberately
        # safety-only: no CAL77 sample/aggregate rule is allowed to change values.
        return self.safety_service.estimate(
            observation,
            external_proposal=external_proposal,
        )


class RuntimeRecognitionService:
    """Run frozen visual recognition first, then deterministic local arbitration."""

    def __init__(
        self,
        base_service: RecognitionService,
        packaging_arbitrator: RuntimePackagingArbitrator,
    ) -> None:
        self.base_service = base_service
        self.packaging_arbitrator = packaging_arbitrator

    def __getattr__(self, name: str):
        return getattr(self.base_service, name)

    def recognize(self, *args, **kwargs):
        observation, proposal = self.base_service.recognize(*args, **kwargs)
        if proposal is None:
            return observation, None
        arbitrated = self.packaging_arbitrator.estimate(
            observation,
            external_proposal=proposal,
        )
        return observation, arbitrated


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
        )
