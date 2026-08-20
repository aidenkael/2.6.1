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
    # 局部重估完整轨迹（后台校准证据，不进历史 UI）：
    # 每条 {reestimate_id, sequence, timestamp, user_correction,
    #        confirmed_facts, input_current_adopted, raw_reestimate_proposal,
    #        adopted_reestimate_proposal, arbitration_trace,
    #        model, provider, prompt_version, accepted}
    reestimate_history: list[dict[str, Any]] = field(default_factory=list)

    def confirm_value(self, field: str, value: Any) -> None:
        """Record a valid user-entered fact in the existing session authority."""
        if field not in self.observation.__dataclass_fields__:
            return
        if value is None or value == "":
            self.user_overrides.pop(field, None)
            self.confirmed_fields.discard(field)
            self.field_sources.pop(field, None)
            return
        self.user_overrides[field] = value
        self.confirmed_fields.add(field)
        self.field_sources[field] = "user_confirmed"

    def reset_facts(self) -> None:
        """Clear all user-confirmed facts (history reload rebuilds them from the record)."""
        self.user_overrides.clear()
        self.confirmed_fields.clear()
        self.field_sources.clear()

    def append_reestimate(self, entry: dict[str, Any]) -> bool:
        """Record one local-reestimate attempt; dedup by stable reestimate_id.

        Returns True when appended, False when a duplicate id was ignored.
        """
        entry = dict(entry)
        identifier = str(entry.get("reestimate_id") or "").strip()
        if identifier:
            existing_ids = {
                str(item.get("reestimate_id") or "")
                for item in self.reestimate_history
                if isinstance(item, dict)
            }
            if identifier in existing_ids:
                return False
        if not entry.get("sequence"):
            entry["sequence"] = len(self.reestimate_history) + 1
        self.reestimate_history.append(entry)
        return True

    def confirmed_facts(self) -> dict[str, dict[str, Any]]:
        meanings = {
            "weight_g": "total net weight of all currently purchased/selected items in grams; do not multiply by purchase_quantity",
            "length_cm": "unpacked item length in centimetres",
            "width_cm": "unpacked item width in centimetres",
            "height_cm": "unpacked item height in centimetres",
            "product_cost_rmb": "product cost in RMB",
            "domestic_shipping_rmb": "domestic shipping in RMB",
        }
        return {
            field: {"value": value, "source": "user_confirmed", "meaning": meanings.get(field, field)}
            for field, value in self.user_overrides.items()
            if field in self.confirmed_fields and value is not None
        }

    def protect_confirmed_values(self, observation: AIObservation) -> dict[str, dict[str, Any]]:
        """Keep user facts authoritative while retaining AI disagreement for diagnostics."""
        conflicts: dict[str, dict[str, Any]] = {}
        for field, value in self.user_overrides.items():
            if field not in self.confirmed_fields or field not in observation.__dataclass_fields__:
                continue
            ai_value = getattr(observation, field)
            if ai_value is not None and ai_value != value:
                conflicts[field] = {"user_confirmed": value, "ai_returned": ai_value}
            setattr(observation, field, value)
            if field == "product_name":
                # The page summary prefers this normalized display field, so it
                # must share the same user-confirmed authority as product_name.
                observation.display_product_summary = str(value)
        if "weight_g" in self.confirmed_fields:
            observation.weight_scope = "net_weight"
        if any(field in self.confirmed_fields for field in ("length_cm", "width_cm", "height_cm")):
            observation.dimension_scope = "product_size"
        if conflicts:
            observation.raw_payload.setdefault("user_confirmed_conflicts", {}).update(conflicts)
        return conflicts

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
