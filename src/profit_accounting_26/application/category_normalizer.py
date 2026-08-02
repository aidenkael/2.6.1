from __future__ import annotations

import json
from pathlib import Path

from profit_accounting_26.domain.models import AIObservation


def _aliases() -> dict:
    path = Path(__file__).resolve().parents[3] / "config" / "category_aliases.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def normalize_observation(observation: AIObservation) -> AIObservation:
    """Keep AI wording for display while giving CAL a stable, local code."""
    raw = observation.product_type_raw or observation.product_type
    haystack = " ".join(str(value or "").lower() for value in (raw, observation.product_name, observation.product_family))
    for key, value in _aliases().items():
        if any(alias.lower() in haystack for alias in value.get("aliases", [])):
            observation.product_family_code = str(value.get("family_code") or key)
            observation.product_family = observation.product_family or ("袜类" if key == "hosiery" else "软质纺织品")
            if key == "hosiery":
                observation.product_type_code = "split_toe_socks" if any(word in haystack for word in ("分趾", "二趾", "split toe", "tabi")) else "hosiery"
            else:
                observation.product_type_code = key
            return _normalize_physical_structure(observation)
    observation.product_type_code = observation.product_type_code if observation.product_type_code != "unknown" else "unknown"
    observation.product_family_code = observation.product_family_code if observation.product_family_code != "unknown" else "unknown"
    return _normalize_physical_structure(observation)


def _normalize_physical_structure(observation: AIObservation) -> AIObservation:
    """Derive only safe transport-form defaults for older AI responses.

    Material hardness is deliberately not used as a synonym for a rigid,
    shape-retained product.
    """
    observation.packing_actions = [str(value) for value in (observation.packing_actions or []) if str(value)]
    observation.packing_constraints = [str(value) for value in (observation.packing_constraints or []) if str(value)]
    if observation.overall_form != "unknown":
        return observation
    if observation.requires_shape_retention is True:
        observation.overall_form = "hard_3d"
    elif "coil" in observation.packing_actions:
        observation.overall_form = "flexible_chain"
    elif "flat_fold" in observation.packing_actions:
        observation.overall_form = "soft_flat"
    elif observation.rigidity == "soft" and observation.foldability == "good":
        observation.overall_form = "soft_flat"
    return observation
