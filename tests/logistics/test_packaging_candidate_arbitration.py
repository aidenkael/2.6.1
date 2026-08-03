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


def test_foldable_item_uses_transformed_transport_outline_before_generic_candidate():
    proposal = PackagingEstimationService().estimate(
        AIObservation(product_name="generic flexible strip", length_cm=55, width_cm=2, height_cm=1,
                      weight_g=110, foldability="good", packing_actions=["flat_fold"]),
    )
    assert proposal.normal.length_cm < 55
    assert proposal.normal.weight_g >= 110


def test_nonfoldable_item_keeps_outline_and_ai_cannot_drop_confirmed_net_weight():
    observation = AIObservation(product_name="generic rigid item", length_cm=55, width_cm=2, height_cm=1,
                                weight_g=110, foldability="none", packing_constraints=["longest_nonfoldable_axis"])
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(_scenario("normal", dims=(56, 3, 2), weight=100)),
    )
    assert "packaged_weight_below_confirmed_net_weight" in proposal.rejected_candidates["ai_candidate"]


def test_ai_fold_claim_without_smaller_outline_is_rejected_and_fallback_continues():
    observation = AIObservation(
        product_name="generic flexible item", length_cm=60, width_cm=10, height_cm=2, weight_g=110,
        dimension_scope="product_size", foldability="good", packing_actions=["flat_fold"],
    )
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(_scenario("normal", state=PackagingState.FULL_FLAT_FOLD, dims=(60, 10, 2), weight=130)),
    )
    assert "packing_action_not_reflected_in_outline" in proposal.rejected_candidates["ai_candidate"]
    assert proposal.proposal_source == "generic_candidate"


def test_unsupported_box_with_no_weight_increment_is_rejected():
    observation = AIObservation(product_name="generic flexible item", weight_g=110, weight_scope="net_weight")
    boxed = _scenario("normal", dims=(20, 15, 6), weight=110)
    boxed.packaging_method = "paper box"
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(boxed, _scenario("conservative", dims=(22, 17, 8), weight=130)),
    )
    reasons = proposal.rejected_candidates["ai_candidate"]
    assert "unsupported_individual_package_type" in reasons
    assert "packaged_weight_has_no_material_increment" in reasons


def test_recognizable_item_with_confirmed_weight_and_no_outer_dimensions_gets_candidate():
    proposal = PackagingEstimationService().estimate(
        AIObservation(product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
                      weight_g=110, weight_scope="net_weight"),
    )
    assert proposal.proposal_source == "generic_candidate"
    assert proposal.normal.is_complete()
    assert proposal.normal.weight_g > 110


def test_semantically_rejected_ai_outline_is_not_reused_by_fallback():
    observation = AIObservation(
        product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
        weight_g=110, weight_scope="net_weight",
        raw_payload={"dimension_semantic_issue": "dimension_evidence_not_outer_dimensions"},
    )
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(_scenario("normal", dims=(55, 70, 2.5), weight=130)),
    )
    assert "dimension_evidence_not_outer_dimensions" in proposal.rejected_candidates["ai_candidate"]
    assert proposal.proposal_source == "generic_candidate"
    assert proposal.normal.length_cm < 55
