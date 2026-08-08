"""Offline layered replay of the production vision/packaging chain.

The replay runs EXACTLY four layers, all through production code, and never
issues a network request:

    AI_RAW       provider response content JSON exactly as the model wrote it
    PARSED       production numeric cleaning + ``AIObservation.from_dict``
                 (before ``normalize_observation``)
    NORMALIZED   ``RecognitionService.parse_payload`` output (normalization,
                 dimension semantic gate, vision completion included)
    FINAL        ``PackagingEstimationService.estimate`` output

Comparing the same field across layers answers the core evaluation question:
"某个数值究竟在哪一层被改变？" (at which layer did a value change?).

Legacy note: the current production engine emits a ``normal``/``conservative``
scenario pair. Both are reported under ``legacy_current_engine_output`` so
future V2 code never mistakes them for the long-term data standard. The V2
single primary result shape (``estimated_package``) is derived from the
adopted normal scenario for forward compatibility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.domain.models import AIObservation
from profit_accounting_26.shared import resource_path

from .case_io import EvalCase

OBSERVATION_DIMENSION_FIELDS = ("length_cm", "width_cm", "height_cm", "weight_g")


@dataclass
class LayeredReplay:
    case_id: str
    origin: str
    model: str
    ai_raw_payload: dict[str, Any] = field(default_factory=dict)
    ai_raw_candidate: dict[str, Any] | None = None
    parsed_observation: dict[str, Any] = field(default_factory=dict)
    parsed_issues: dict[str, Any] = field(default_factory=dict)
    normalized_observation: dict[str, Any] = field(default_factory=dict)
    external_proposal: dict[str, Any] | None = None
    final: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        final = self.final if isinstance(self.final, dict) else {}
        normal = final.get("normal") if isinstance(final.get("normal"), dict) else {}
        conservative = final.get("conservative") if isinstance(final.get("conservative"), dict) else {}
        return {
            "case_id": self.case_id,
            "origin": self.origin,
            "model": self.model,
            "error": self.error,
            "layers": {
                "AI_RAW": {
                    "observation": self.ai_raw_payload.get("observation"),
                    "packaging_proposal": self.ai_raw_candidate,
                },
                "PARSED": {"observation": self.parsed_observation, "numeric_parse_issues": self.parsed_issues},
                "NORMALIZED": {"observation": self.normalized_observation, "external_proposal": self.external_proposal},
                "FINAL": {
                    **final,
                    # 当前引擎的 normal/conservative 双档输出是历史遗留格式，
                    # 明确标记为 legacy，避免被未来 V2 代码当成长期数据标准。
                    "legacy_current_engine_output": {
                        "normal": normal,
                        "conservative": conservative,
                    },
                    # V2 单一主包装结果预留：从被采纳的正常档派生。
                    "estimated_package": _derive_estimated_package(normal),
                },
            },
            "trace": self.trace,
        }


def build_baseline_service() -> PackagingEstimationService:
    """Build the service exactly like production ``AppContext.create_default``.

    Read-only: it reuses the repository calibration files directly instead of
    copying them into the user data directory, so replay results match the
    shipped baseline rules.
    """
    return PackagingEstimationService(
        resource_path("calibration/logistics_v2/calibration_all_cleaned_v3.json"),
        calibration_version=PackagingEstimationService.CALIBRATION_VERSION,
        rule_registry_path=resource_path("calibration/logistics_v2/packaging_rule_registry_v1.json"),
    )


def _derive_estimated_package(normal: dict[str, Any]) -> dict[str, Any] | None:
    """Derive the V2 single primary package from the legacy normal scenario."""
    if not normal:
        return None
    return {
        "length_cm": normal.get("length_cm"),
        "width_cm": normal.get("width_cm"),
        "height_cm": normal.get("height_cm"),
        "weight_g": normal.get("weight_g"),
        "packaging_method": normal.get("packaging_method"),
        "derived_from": "legacy_current_engine_output.normal",
    }


def _build_trace(proposal) -> dict[str, Any]:
    records = proposal.candidate_records or {}
    coordination = records.get("cal_coordination") or {}
    salvage = records.get("candidate_field_salvage") or {}
    return {
        "proposal_source": proposal.proposal_source,
        "final_candidate": {"normal": proposal.normal.to_dict(), "conservative": proposal.conservative.to_dict()},
        "candidate_records": records,
        "rejected_candidates": proposal.rejected_candidates,
        "cal_adjustments": {
            "rule_id": coordination.get("rule_id"),
            "match_strength": coordination.get("match_strength"),
            "adjusted_fields": coordination.get("adjusted_fields", {}),
            "risk_only": coordination.get("risk_only", False),
        },
        "salvage_adjustments": {
            "diagnostic": salvage.get("diagnostic"),
            "adjustments": salvage.get("adjustments", []),
            "rejection_reasons": salvage.get("rejection_reasons", []),
        },
        "structural_adjustments": list(proposal.adjustments or []),
        "applied_profile_ids": list(proposal.applied_profile_ids or []),
        "review_reasons": list(proposal.review_reasons or []),
    }


def replay_case(case: EvalCase, service: PackagingEstimationService, *, model: str | None = None) -> LayeredReplay:
    """Replay one saved case through the production chain. No API call."""
    replay = LayeredReplay(
        case_id=case.case_id,
        origin=case.origin,
        model=str(model or case.raw_response.get("model") or case.metadata.get("model") or "unknown-model"),
    )
    try:
        # --- AI_RAW: exactly what the provider returned inside content ------
        content = RecognitionService._extract_content(case.raw_response)
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("AI 返回根节点必须是 JSON 对象")
        replay.ai_raw_payload = payload
        raw_candidate = payload.get("packaging_proposal")
        replay.ai_raw_candidate = raw_candidate if isinstance(raw_candidate, dict) else None

        # --- PARSED: production numeric cleaning only, no normalization -----
        raw_observation = payload.get("observation")
        if not isinstance(raw_observation, dict):
            raw_observation = payload
        parse_issues: dict[str, dict[str, Any]] = {}
        cleaned = RecognitionService._clean_numeric_fields(
            raw_observation, prefix="observation", parse_issues=parse_issues,
        )
        replay.parsed_observation = AIObservation.from_dict(cleaned).to_dict()
        replay.parsed_issues = parse_issues

        # --- NORMALIZED: full production parser ------------------------------
        observation, proposal = RecognitionService.parse_payload(case.raw_response, model=replay.model)
        replay.normalized_observation = observation.to_dict()
        replay.external_proposal = proposal.to_dict() if proposal else None

        # --- FINAL: production arbitration -----------------------------------
        final = service.estimate(observation, external_proposal=proposal)
        replay.final = final.to_dict()
        replay.trace = _build_trace(final)
    except Exception as exc:  # noqa: BLE001 - a broken case must not abort the run
        replay.error = f"{type(exc).__name__}: {exc}"
    return replay


def dimension_journey(replay: LayeredReplay) -> dict[str, dict[str, Any]]:
    """Follow length/width/height/weight through all four layers.

    AI_RAW..NORMALIZED show the observation-level value; FINAL shows the
    adopted normal packaging scenario value.
    """
    journey: dict[str, dict[str, Any]] = {}
    final_normal = (replay.final.get("normal") or {}) if isinstance(replay.final, dict) else {}
    raw_observation = replay.ai_raw_payload.get("observation")
    raw_observation = raw_observation if isinstance(raw_observation, dict) else replay.ai_raw_payload
    for field_name in OBSERVATION_DIMENSION_FIELDS:
        journey[field_name] = {
            "AI_RAW": raw_observation.get(field_name),
            "PARSED": replay.parsed_observation.get(field_name),
            "NORMALIZED": replay.normalized_observation.get(field_name),
            "FINAL": final_normal.get(field_name),
        }
    return journey
