from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from profit_accounting_26.domain.models import AIObservation, PackagingProposal


@dataclass(slots=True)
class CalculationSession:
    """Single in-memory authority for one SKU calculation session."""

    images: list[dict[str, str]] = field(default_factory=list)
    ai_raw_response: dict[str, Any] = field(default_factory=dict)
    ai_raw_observation: dict[str, Any] = field(default_factory=dict)
    observation: AIObservation = field(default_factory=AIObservation)
    normalized_observation: AIObservation = field(default_factory=AIObservation)
    user_overrides: dict[str, Any] = field(default_factory=dict)
    confirmed_fields: set[str] = field(default_factory=set)
    field_sources: dict[str, str] = field(default_factory=dict)
    field_confidence: dict[str, str] = field(default_factory=dict)
    money_candidates: list[dict[str, Any]] = field(default_factory=list)
    matched_cal_rules: list[str] = field(default_factory=list)
    rejected_cal_rules: list[dict[str, Any]] = field(default_factory=list)
    ai_packaging_proposal: PackagingProposal | None = None
    local_packaging_proposal: PackagingProposal | None = None
    calibration_result: PackagingProposal | None = None
    adopted_packaging: PackagingProposal | None = None
    calculation_result: dict[str, Any] = field(default_factory=dict)
    rule_trace: list[str] = field(default_factory=list)

    def apply_observation_patch(self, patch: dict[str, Any]) -> list[str]:
        changed: list[str] = []
        allowed = self.observation.__dataclass_fields__.keys()
        for key, value in patch.items():
            if key not in allowed or key in self.user_overrides:
                continue
            if getattr(self.observation, key) != value:
                setattr(self.observation, key, value)
                changed.append(key)
        return changed

    def adopt(self, proposal: PackagingProposal) -> None:
        self.calibration_result = proposal
        self.local_packaging_proposal = proposal
        self.adopted_packaging = proposal
        self.matched_cal_rules = list(proposal.applied_profile_ids)
