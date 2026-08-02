from profit_accounting_26.application.category_normalizer import normalize_observation
from profit_accounting_26.domain.models import AIObservation


def test_hosiery_aliases_normalize_to_the_same_local_family():
    values = ["袜子", "女袜", "丝袜", "分趾袜", "socks", "hosiery", "split toe socks"]
    normalized = [normalize_observation(AIObservation(product_type=value)) for value in values]
    assert {item.product_family_code for item in normalized} == {"hosiery"}


def test_flexible_slender_structure_without_bulky_evidence_is_not_soft_bulky():
    observation = normalize_observation(AIObservation(
        product_type="flexible slender item", overall_form="soft_bulky", packing_actions=["coil"],
    ))
    assert observation.overall_form == "flexible_chain"


def test_split_toe_alias_keeps_display_text_but_uses_stable_code():
    observation = normalize_observation(AIObservation(product_type="分趾女袜"))
    assert observation.product_type == "分趾女袜"
    assert observation.product_type_code == "split_toe_socks"
