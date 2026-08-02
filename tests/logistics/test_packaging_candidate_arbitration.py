from __future__ import annotations

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState


def _scenario(label: str, *, state: PackagingState = PackagingState.MODERATE_COMPRESSION,
              dims: tuple[float, float, float] = (18, 12, 3), weight: float = 100) -> PackagingScenario:
    return PackagingScenario(label=label, packaging_state=state, packaging_method="vision proposal",
                             length_cm=dims[0], width_cm=dims[1], height_cm=dims[2], weight_g=weight)


def _ai(normal: PackagingScenario | None = None, conservative: PackagingScenario | None = None) -> PackagingProposal:
    return PackagingProposal(normal=normal or _scenario("normal"),
                             conservative=conservative or _scenario("conservative", dims=(20, 14, 4), weight=130),
                             proposal_source="vision_api")


def test_hard_flat_complete_ai_candidate_is_not_forced_to_shape_retained():
    proposal = PackagingEstimationService().estimate(
        AIObservation(overall_form="hard_flat", rigidity="hard"), external_proposal=_ai())
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.packaging_state is not PackagingState.SHAPE_RETAINED


def test_flexible_chain_hard_material_is_not_shape_retained():
    proposal = PackagingEstimationService().estimate(
        AIObservation(overall_form="flexible_chain", rigidity="hard", packing_actions=["coil"]), external_proposal=_ai())
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.packaging_state is not PackagingState.SHAPE_RETAINED


def test_complete_self_consistent_ai_candidate_wins_arbitration():
    proposal = PackagingEstimationService().estimate(AIObservation(), external_proposal=_ai())
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.candidate_records["ai_candidate"]["rejection_reasons"] == []


def test_ai_candidate_violating_no_compress_is_rejected_with_reason():
    proposal = PackagingEstimationService().estimate(
        AIObservation(packing_constraints=["do_not_compress"]),
        external_proposal=_ai(_scenario("normal", state=PackagingState.STRONG_COMPRESSION)),
    )
    assert "ai_candidate" in proposal.rejected_candidates
    assert "violates_do_not_compress" in proposal.rejected_candidates["ai_candidate"]


def test_merchant_shipping_package_facts_override_ai_candidate():
    proposal = PackagingEstimationService().estimate(
        AIObservation(length_cm=30, width_cm=20, height_cm=10, weight_g=500,
                      dimension_scope="shipping_package_size", weight_scope="packaged_weight"),
        external_proposal=_ai(),
    )
    assert proposal.proposal_source == "merchant_candidate"
    assert proposal.normal.length_cm == 30
    assert proposal.normal.weight_g == 500


def test_selected_result_keeps_conservative_values_monotonic():
    proposal = PackagingEstimationService().estimate(AIObservation(), external_proposal=_ai())
    assert proposal.conservative.length_cm >= proposal.normal.length_cm
    assert proposal.conservative.width_cm >= proposal.normal.width_cm
    assert proposal.conservative.height_cm >= proposal.normal.height_cm
    assert proposal.conservative.weight_g >= proposal.normal.weight_g
