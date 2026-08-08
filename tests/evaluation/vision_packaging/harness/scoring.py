"""Layered scoring for vision/packaging evaluation cases.

Design rules fixed by the evaluation charter:

* No single overall score. Accuracy is reported PER LAYER:
  ``ai_candidate`` (model output), ``parsed`` (after parser), ``final``
  (after local arbitration).
* Dimensions/weights are graded against human acceptable RANGES, never by
  exact equality. A ground-truth field left ``null``/``unknown`` is skipped.
* Packaging methods are graded against an ``acceptable_methods`` set using
  bidirectional substring matching (methods are free-form Chinese text).
* The headline metric is ``post_ai_degradation_rate``:
  cases where AI was correct but FINAL is wrong, divided by cases where AI
  was correct.
* Business-level metrics (chargeable weight / shipping cost error) are only
  computed when the case carries real ``actual_feedback`` facts; otherwise
  they report ``"unavailable"`` and are NEVER fabricated. The replay harness
  does not run the logistics engine, so ``shipping_cost_error`` is always
  ``"unavailable"`` in this round.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .replay import LayeredReplay

_AXIS_RANGES = ("length_range", "width_range", "height_range")
_AXIS_FIELDS = ("length_cm", "width_cm", "height_cm")


def coerce_number(value: Any) -> float | None:
    """Best-effort numeric coercion for raw AI values like ``"22cm"``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*(?:约\s*)?([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[a-zA-Z%]*\s*", str(value))
    return float(match.group(1)) if match else None


def _in_range(value: float | None, pair: Any) -> bool:
    if value is None:
        return False
    lo, hi = float(pair[0]), float(pair[1])
    return lo <= float(value) <= hi


def _normalize_method_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def grade_method(method_text: Any, acceptable_methods: Any) -> bool | None:
    """None = not graded. ``"*"`` accepts any non-empty method."""
    if not isinstance(acceptable_methods, list) or not acceptable_methods:
        return None
    candidate = _normalize_method_text(method_text)
    for entry in acceptable_methods:
        entry_text = _normalize_method_text(entry)
        if entry_text in {"*", "any", "任意"}:
            return bool(candidate)
        if entry_text and (entry_text in candidate or (candidate and candidate in entry_text)):
            return True
    return False


@dataclass
class CandidateVerdict:
    dimensions: bool | None = None
    weight: bool | None = None
    method: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def graded(self) -> bool:
        return any(value is not None for value in (self.dimensions, self.weight, self.method))

    @property
    def correct(self) -> bool | None:
        graded_values = [value for value in (self.dimensions, self.weight, self.method) if value is not None]
        if not graded_values:
            return None
        return all(graded_values)


def score_packaging_candidate(scenario: dict[str, Any] | None, packaging_truth: dict[str, Any] | None) -> CandidateVerdict:
    """Grade one packaging scenario (normal tier) against ground truth."""
    verdict = CandidateVerdict()
    if not isinstance(packaging_truth, dict) or packaging_truth.get("unknown") is True:
        return verdict
    scenario = scenario if isinstance(scenario, dict) else {}
    graded_any = False
    axis_pairs = [pair for pair in (packaging_truth.get(axis) for axis in _AXIS_RANGES) if pair is not None]
    if axis_pairs:
        graded_any = True
        values = [coerce_number(scenario.get(field_name)) for field_name in _AXIS_FIELDS]
        pairs = [packaging_truth.get(axis) for axis in _AXIS_RANGES]
        verdict.dimensions = all(
            True if pair is None else _in_range(value, pair)
            for value, pair in zip(values, pairs)
        )
        verdict.details["dimensions"] = {
            field_name: {"value": value, "range": pair}
            for field_name, value, pair in zip(_AXIS_FIELDS, values, pairs)
        }
    weight_pair = packaging_truth.get("weight_range")
    if weight_pair is not None:
        graded_any = True
        weight = coerce_number(scenario.get("weight_g"))
        verdict.weight = _in_range(weight, weight_pair)
        verdict.details["weight"] = {"value": weight, "range": weight_pair}
    methods = packaging_truth.get("acceptable_methods")
    if isinstance(methods, list) and methods:
        graded_any = True
        verdict.method = grade_method(scenario.get("packaging_method"), methods)
        verdict.details["method"] = {"value": scenario.get("packaging_method"), "acceptable": methods}
    if not graded_any:
        return CandidateVerdict()
    return verdict


def _ai_raw_normal(replay: LayeredReplay) -> dict[str, Any] | None:
    candidate = replay.ai_raw_candidate
    if not isinstance(candidate, dict):
        return None
    normal = candidate.get("normal")
    return normal if isinstance(normal, dict) else None


def _external_normal(replay: LayeredReplay) -> dict[str, Any] | None:
    proposal = replay.external_proposal
    if not isinstance(proposal, dict):
        return None
    normal = proposal.get("normal")
    return normal if isinstance(normal, dict) else None


def _final_normal(replay: LayeredReplay) -> dict[str, Any] | None:
    final = replay.final
    if not isinstance(final, dict):
        return None
    normal = final.get("normal")
    return normal if isinstance(normal, dict) else None


@dataclass
class CaseScore:
    case_id: str
    origin: str
    replay_ok: bool
    ai: CandidateVerdict
    parsed: CandidateVerdict
    final: CandidateVerdict
    local_effect: str  # improved | unchanged | degraded | not_graded
    error: str | None = None
    estimated_package: CandidateVerdict | None = None  # V2 单一主结果评分（可选）
    business_metrics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        estimated = (
            {"correct": self.estimated_package.correct, "dimensions": self.estimated_package.dimensions,
             "weight": self.estimated_package.weight, "method": self.estimated_package.method,
             "details": self.estimated_package.details}
            if self.estimated_package is not None else None
        )
        return {
            "case_id": self.case_id,
            "origin": self.origin,
            "replay_ok": self.replay_ok,
            "error": self.error,
            "local_effect": self.local_effect,
            "verdicts": {
                "ai_candidate": {"correct": self.ai.correct, "dimensions": self.ai.dimensions,
                                  "weight": self.ai.weight, "method": self.ai.method, "details": self.ai.details},
                "parsed": {"correct": self.parsed.correct, "dimensions": self.parsed.dimensions,
                            "weight": self.parsed.weight, "method": self.parsed.method, "details": self.parsed.details},
                "final": {"correct": self.final.correct, "dimensions": self.final.dimensions,
                           "weight": self.final.weight, "method": self.final.method, "details": self.final.details},
                "estimated_package": estimated,
            },
            "business_metrics": self.business_metrics,
        }


def _local_effect(ai: CandidateVerdict, final: CandidateVerdict) -> str:
    if ai.correct is None or final.correct is None:
        return "not_graded"
    if ai.correct and not final.correct:
        return "degraded"
    if not ai.correct and final.correct:
        return "improved"
    return "unchanged"


SEVERE_UNDERESTIMATE_RATIO = 0.9


def score_business_metrics(replay: LayeredReplay, ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Business-level error metrics, computed ONLY from real case facts.

    Every metric reports ``"unavailable"`` when the required fact is missing;
    nothing is fabricated. The replay harness does not call the production
    logistics engine, so ``shipping_cost_error`` is unavailable by design in
    this round (actual fees alone cannot yield an estimated fee).
    """
    result: dict[str, Any] = {
        "chargeable_weight_error": "unavailable",
        "shipping_cost_error": "unavailable",
        "underestimate": "unavailable",
        "severe_underestimate": "unavailable",
    }
    truth = ground_truth if isinstance(ground_truth, dict) else {}
    actual = truth.get("actual_feedback")
    actual = actual if isinstance(actual, dict) else {}
    actual_kg = coerce_number(actual.get("actual_chargeable_weight_kg"))
    final_normal = _final_normal(replay) if replay.ok else None
    estimate_g = coerce_number((final_normal or {}).get("weight_g"))
    if actual_kg is not None and estimate_g is not None:
        estimate_kg = estimate_g / 1000.0
        result["chargeable_weight_error"] = round(estimate_kg - actual_kg, 4)
        result["underestimate"] = estimate_kg < actual_kg
        result["severe_underestimate"] = estimate_kg < actual_kg * SEVERE_UNDERESTIMATE_RATIO
    if actual.get("actual_first_mile_fee_rmb") is not None:
        result["shipping_cost_error"] = "unavailable_no_logistics_replay"
    return result


def score_case(replay: LayeredReplay, ground_truth: dict[str, Any]) -> CaseScore:
    if not replay.ok:
        empty = CandidateVerdict()
        return CaseScore(replay.case_id, replay.origin, False, empty, empty, empty, "not_graded", replay.error)
    truth = ground_truth if isinstance(ground_truth, dict) else {}
    packaging_truth = truth.get("normal_packaging")
    ai = score_packaging_candidate(_ai_raw_normal(replay), packaging_truth)
    parsed = score_packaging_candidate(_external_normal(replay), packaging_truth)
    final = score_packaging_candidate(_final_normal(replay), packaging_truth)
    estimated_truth = truth.get("estimated_package")
    estimated = (
        score_packaging_candidate(_final_normal(replay), estimated_truth)
        if isinstance(estimated_truth, dict) else None
    )
    return CaseScore(
        replay.case_id, replay.origin, True, ai, parsed, final, _local_effect(ai, final),
        estimated_package=estimated, business_metrics=score_business_metrics(replay, truth),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def aggregate_metrics(scores: list[CaseScore], *, label: str) -> dict[str, Any]:
    """Aggregate per-layer accuracy and local-processing effects.

    ``post_ai_degradation_rate`` = #(AI correct AND final wrong) / #(AI correct).
    """
    valid = [score for score in scores if score.replay_ok]
    replay_errors = [score for score in scores if not score.replay_ok]

    def layer_accuracy(attr: str) -> tuple[int, int, float | None]:
        gradable = [getattr(score, attr) for score in valid]
        graded = [verdict for verdict in gradable if verdict.correct is not None]
        correct = [verdict for verdict in graded if verdict.correct]
        return len(correct), len(graded), _ratio(len(correct), len(graded))

    ai_correct, ai_graded, ai_accuracy = layer_accuracy("ai")
    parsed_correct, parsed_graded, parsed_accuracy = layer_accuracy("parsed")
    final_correct, final_graded, final_accuracy = layer_accuracy("final")

    effect_counts = {"improved": 0, "unchanged": 0, "degraded": 0, "not_graded": 0}
    for score in valid:
        effect_counts[score.local_effect] += 1
    graded_pairs = effect_counts["improved"] + effect_counts["unchanged"] + effect_counts["degraded"]

    degraded_after_ai = [
        score for score in valid
        if score.ai.correct is True and score.final.correct is False
    ]
    business_available = [
        score for score in valid
        if isinstance(score.business_metrics, dict)
        and score.business_metrics.get("chargeable_weight_error") != "unavailable"
    ]
    errors = [
        score.business_metrics["chargeable_weight_error"] for score in business_available
    ]
    business_summary = {
        "available_cases": len(business_available),
        "unavailable_cases": len(valid) - len(business_available),
        "mean_chargeable_weight_error_kg": round(sum(errors) / len(errors), 4) if errors else None,
        "underestimate_cases": [
            score.case_id for score in business_available
            if score.business_metrics.get("underestimate") is True
        ],
        "severe_underestimate_cases": [
            score.case_id for score in business_available
            if score.business_metrics.get("severe_underestimate") is True
        ],
    }
    return {
        "label": label,
        "cases_total": len(scores),
        "cases_replayed": len(valid),
        "replay_errors": [{"case_id": score.case_id, "error": score.error} for score in replay_errors],
        "ai_candidate_accuracy": {"correct": ai_correct, "graded": ai_graded, "rate": ai_accuracy},
        "parsed_accuracy": {"correct": parsed_correct, "graded": parsed_graded, "rate": parsed_accuracy},
        "final_accuracy": {"correct": final_correct, "graded": final_graded, "rate": final_accuracy},
        "local_processing": {
            **effect_counts,
            "local_improvement_rate": _ratio(effect_counts["improved"], graded_pairs),
        },
        "post_ai_degradation": {
            "count": len(degraded_after_ai),
            "ai_correct_count": ai_correct,
            "cases": [score.case_id for score in degraded_after_ai],
            "post_ai_degradation_rate": _ratio(len(degraded_after_ai), ai_correct),
        },
        "business_metrics": business_summary,
    }
