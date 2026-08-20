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


def test_foldable_item_without_ai_does_not_fabricate_transport_outline():
    proposal = PackagingEstimationService().estimate(
        AIObservation(product_name="generic flexible strip", length_cm=55, width_cm=2, height_cm=1,
                      weight_g=110, foldability="good", packing_actions=["flat_fold"]),
    )
    # 无外部 AI shipment → 不生成 generic/transform 精确尺寸，优先人工复核
    assert proposal.proposal_source == "no_valid_candidate"
    assert not proposal.normal.is_complete()


def test_nonfoldable_item_keeps_outline_and_ai_cannot_drop_confirmed_net_weight():
    observation = AIObservation(product_name="generic rigid item", length_cm=55, width_cm=2, height_cm=1,
                                weight_g=110, foldability="none", packing_constraints=["longest_nonfoldable_axis"])
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(_scenario("normal", dims=(56, 3, 2), weight=100)),
    )
    assert "packaged_weight_below_confirmed_net_weight" in proposal.rejected_candidates["ai_candidate"]


def test_ai_fold_claim_without_smaller_outline_is_soft_warning_only():
    observation = AIObservation(
        product_name="generic flexible item", length_cm=60, width_cm=10, height_cm=2, weight_g=110,
        dimension_scope="product_size", foldability="good", packing_actions=["flat_fold"],
    )
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(
            _scenario("normal", state=PackagingState.FULL_FLAT_FOLD, dims=(60, 10, 2), weight=130),
            _scenario("conservative", state=PackagingState.FULL_FLAT_FOLD, dims=(62, 12, 4), weight=150),
        ),
    )
    # 软语义冲突 → 记录 warning，不替换完整 AI shipment
    assert "packing_action_not_reflected_in_outline" in proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.length_cm == 60


def test_unsupported_box_with_no_weight_increment_is_soft_warning_only():
    observation = AIObservation(product_name="generic flexible item", weight_g=110, weight_scope="net_weight")
    boxed = _scenario("normal", dims=(20, 15, 6), weight=110)
    boxed.packaging_method = "硬质包装盒"
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(boxed, _scenario("conservative", dims=(22, 17, 8), weight=130)),
    )
    warnings = proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert "unsupported_individual_package_type" in warnings
    assert "packaged_weight_has_no_material_increment" in warnings
    assert proposal.proposal_source == "ai_candidate"


def test_single_item_outline_text_is_not_individual_box_evidence():
    observation = AIObservation(
        product_name="generic item",
        raw_payload={"field_evidence": {"dimensions": {"raw_text": "单件三维外廓尺寸 20×10×5cm"}}},
    )
    boxed = _scenario("normal", dims=(22, 12, 7), weight=130)
    boxed.packaging_method = "paper box"
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(boxed, _scenario("conservative", dims=(24, 14, 9), weight=150)),
    )
    # 软语义冲突 → warning，完整 AI shipment 保留
    assert "unsupported_individual_package_type" in proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert proposal.proposal_source == "ai_candidate"


def test_merchant_original_box_evidence_allows_box_claim():
    observation = AIObservation(
        product_name="generic item",
        raw_payload={"field_evidence": {"packaging": {
            "source_image_index": 1, "raw_text": "商家明确原盒，单个/盒",
        }}},
    )
    boxed = _scenario("normal", dims=(22, 12, 7), weight=130)
    boxed.packaging_method = "paper box"
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(boxed, _scenario("conservative", dims=(24, 14, 9), weight=150)),
    )
    assert proposal.proposal_source == "ai_candidate"


def test_display_outline_with_unknown_protrusion_is_soft_warning_only():
    observation = AIObservation(
        product_name="generic structured item", overall_form="hard_3d", rigidity="hard",
        foldability="none", compressibility="none", requires_shape_retention=True,
        protrusion_flattenable=None, length_cm=28.5, width_cm=12, height_cm=21,
        weight_g=700, weight_scope="net_weight", dimension_scope="product_size",
    )
    proposal = PackagingEstimationService().estimate(
        observation,
        external_proposal=_ai(
            _scenario("normal", state=PackagingState.SHAPE_RETAINED, dims=(30.5, 14, 23), weight=750),
            _scenario("conservative", state=PackagingState.SHAPE_RETAINED, dims=(32.5, 16, 25), weight=800),
        ),
    )
    warnings = proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert "shape_retention_requires_rigid_evidence" in warnings
    assert "display_outline_requires_transport_evidence" in warnings
    # 完整 AI shipment 不被软语义冲突替换；仅标记复核
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.length_cm == 30.5
    assert proposal.normal.needs_review is True


def test_limited_compressibility_requires_an_explained_transport_change():
    observation = AIObservation(
        product_name="generic limited item", compressibility="limited", length_cm=20, width_cm=15, height_cm=6,
        weight_g=100, weight_scope="net_weight", dimension_scope="product_size",
    )
    proposal = PackagingEstimationService().estimate(
        observation,
        external_proposal=_ai(
            _scenario("normal", dims=(22, 17, 8), weight=130),
            _scenario("conservative", dims=(24, 19, 10), weight=150),
        ),
    )
    warnings = proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert "declared_transport_adjustment_not_reflected" in warnings
    assert proposal.proposal_source == "ai_candidate"
    assert proposal.normal.needs_review is True


def test_explicit_rigid_frame_allows_shape_retained_candidate():
    observation = AIObservation(
        product_name="generic framed item", overall_form="hard_3d", rigidity="hard",
        foldability="none", compressibility="none", requires_shape_retention=True, has_frame=True,
        raw_payload={"field_evidence": {"structure": {"has_frame": {
            "source_image_index": 1, "region_description": "商品中部可见刚性框架", "confidence": "high",
        }}}},
    )
    proposal = PackagingEstimationService().estimate(
        observation,
        external_proposal=_ai(
            _scenario("normal", state=PackagingState.SHAPE_RETAINED, dims=(30, 20, 10), weight=500),
            _scenario("conservative", state=PackagingState.SHAPE_RETAINED, dims=(32, 22, 12), weight=550),
        ),
    )
    assert proposal.proposal_source == "ai_candidate"


def test_unverified_ai_rigid_boolean_is_soft_warning_only():
    observation = AIObservation(
        product_name="generic structured item", overall_form="hard_3d", rigidity="hard",
        foldability="none", compressibility="none", requires_shape_retention=True, has_frame=True,
        length_cm=28.5, width_cm=12, height_cm=21, weight_g=700,
        weight_scope="net_weight", dimension_scope="product_size",
    )
    proposal = PackagingEstimationService().estimate(
        observation,
        external_proposal=_ai(
            _scenario("normal", state=PackagingState.SHAPE_RETAINED, dims=(28.5, 12, 21), weight=750),
            _scenario("conservative", state=PackagingState.SHAPE_RETAINED, dims=(30.5, 14, 23), weight=800),
        ),
    )
    warnings = proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert "shape_retention_requires_rigid_evidence" in warnings
    assert "display_outline_requires_transport_evidence" in warnings
    assert proposal.proposal_source == "ai_candidate"


def test_recognizable_item_with_confirmed_weight_and_no_outer_dimensions_requires_review():
    proposal = PackagingEstimationService().estimate(
        AIObservation(product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
                      weight_g=110, weight_scope="net_weight"),
    )
    # 无外部 AI shipment → 不自动生成 generic 精确尺寸
    assert proposal.proposal_source == "no_valid_candidate"
    assert not proposal.normal.is_complete()
    assert proposal.needs_review


def test_semantically_rejected_ai_outline_is_not_reused_by_fallback():
    observation = AIObservation(
        product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
        weight_g=110, weight_scope="net_weight",
        raw_payload={"dimension_semantic_issue": "dimension_evidence_not_outer_dimensions"},
    )
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(_scenario("normal", dims=(55, 70, 2.5), weight=130)),
    )
    # 页面硬事实（维度证据非外廓）→ 本地不自行创造数值，标记复核
    assert "dimension_evidence_not_outer_dimensions" in proposal.rejected_candidates["ai_candidate"]
    assert proposal.proposal_source == "ai_candidate_hard_facts"
    assert proposal.normal.needs_review is True


def test_invalid_ai_dimensions_keep_confirmed_weight_as_packaged_weight_start():
    observation = AIObservation(
        product_name="generic flexible item", overall_form="flexible_chain", foldability="good",
        packing_actions=["coil"], requires_shape_retention=True, weight_g=110, weight_scope="net_weight",
    )
    partial = _scenario("normal", dims=(20, 15, 2), weight=130)
    partial.length_cm = None
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(partial, _scenario("conservative", dims=(22, 17, 4), weight=145)),
    )
    # AI shipment 不完整 → 保留 AI 有效字段，标记复核，不自动补齐
    assert proposal.proposal_source == "ai_candidate_needs_review"
    assert proposal.normal.weight_g == 130
    assert proposal.normal.weight_g >= 110
    assert proposal.normal.length_cm is None
    assert proposal.needs_review


def test_unsupported_shape_retention_is_removed_without_losing_coil_structure():
    observation = AIObservation(
        product_name="generic flexible item", overall_form="flexible_chain", foldability="good",
        packing_actions=["coil", "retain_shape"], requires_shape_retention=True, weight_g=110, weight_scope="net_weight",
    )
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(
            _scenario("normal", state=PackagingState.SHAPE_RETAINED, dims=(30, 20, 8), weight=140),
            _scenario("conservative", state=PackagingState.SHAPE_RETAINED, dims=(32, 22, 10), weight=160),
        ),
    )
    # 结构词保形证据不足 → warning；完整 AI shipment 保留
    assert proposal.proposal_source == "ai_candidate"
    assert "shape_retention_requires_rigid_evidence" in proposal.candidate_records["ai_candidate"].get("warnings", [])
    assert proposal.normal.needs_review is True


def test_salvage_completes_only_missing_dimensions_and_keeps_valid_weight():
    observation = AIObservation(product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
                                weight_g=110, weight_scope="net_weight")
    partial = _scenario("normal", dims=(20, 15, 2), weight=150)
    partial.height_cm = None
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(partial, _scenario("conservative", dims=(23, 18, 4), weight=170)),
    )
    # AI shipment 不完整 → 保留有效字段 + needs_review，不自动补齐缺失尺寸
    assert proposal.normal.weight_g == 150
    assert proposal.normal.height_cm is None
    assert proposal.needs_review


def test_salvage_completes_only_missing_weight_and_keeps_valid_dimensions():
    observation = AIObservation(product_name="generic flexible item", overall_form="flexible_chain", packing_actions=["coil"],
                                weight_g=110, weight_scope="net_weight")
    missing_weight = _scenario("normal", dims=(18, 12, 3), weight=1)
    missing_weight.weight_g = None
    proposal = PackagingEstimationService().estimate(
        observation, external_proposal=_ai(missing_weight, _scenario("conservative", dims=(20, 14, 4), weight=150)),
    )
    assert (proposal.normal.length_cm, proposal.normal.width_cm, proposal.normal.height_cm) == (18, 12, 3)
    assert proposal.normal.weight_g is None
    assert proposal.needs_review


def test_full_generic_fallback_is_marked_when_only_identity_is_known():
    proposal = PackagingEstimationService().estimate(AIObservation(product_name="generic item"))
    # 无外部 AI shipment → 不生成 generic 兜底，优先人工补充/复核
    assert proposal.proposal_source == "no_valid_candidate"
    assert not proposal.normal.is_complete()
    assert proposal.needs_review
