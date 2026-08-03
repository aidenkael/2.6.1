from profit_accounting_26.application.calculation_session import CalculationSession
from profit_accounting_26.domain.models import PackagingProposal, PackagingScenario


def test_adopted_packaging_is_the_single_local_packaging_authority():
    proposal = PackagingProposal(normal=PackagingScenario(label="normal", length_cm=1, width_cm=1, height_cm=1, weight_g=1), conservative=PackagingScenario(label="conservative", length_cm=2, width_cm=2, height_cm=2, weight_g=2), applied_profile_ids=["CAL-1"])
    session = CalculationSession()
    session.adopt(proposal)
    assert session.adopted_packaging is proposal
    assert session.local_packaging_proposal is proposal
    assert session.matched_cal_rules == ["CAL-1"]


def test_patch_never_overrides_user_confirmed_value():
    session = CalculationSession()
    session.user_overrides["weight_g"] = 99
    changed = session.apply_observation_patch({"weight_g": 12, "rigidity": "soft"})
    assert changed == ["rigidity"]
    assert session.observation.weight_g is None
    assert session.observation.rigidity == "soft"


def test_confirmed_facts_are_serialized_and_win_over_ai_observation():
    session = CalculationSession()
    session.confirm_value("weight_g", 110)
    session.confirm_value("length_cm", 55)
    facts = session.confirmed_facts()
    assert facts["weight_g"]["source"] == "user_confirmed"
    assert facts["weight_g"]["value"] == 110

    observation = session.observation
    observation.weight_g = 100
    observation.length_cm = 50
    conflicts = session.protect_confirmed_values(observation)
    assert observation.weight_g == 110
    assert observation.length_cm == 55
    assert observation.weight_scope == "net_weight"
    assert set(conflicts) == {"weight_g", "length_cm"}
