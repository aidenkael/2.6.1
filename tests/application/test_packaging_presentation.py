from profit_accounting_26.application.packaging_presentation import normal_reminder, packaging_summary, product_summary
from profit_accounting_26.domain.models import AIObservation, PackagingProposal, PackagingScenario, PackagingState


def _proposal(source: str = "ai_candidate", *, state: PackagingState = PackagingState.MODERATE_COMPRESSION,
              confidence: str = "high") -> PackagingProposal:
    normal = PackagingScenario("正常档", state, "internal_method", 20, 12, 4, 120, confidence=confidence, needs_review=False)
    conservative = PackagingScenario("保守档", state, "internal_method", 22, 14, 6, 150, confidence=confidence, needs_review=False)
    return PackagingProposal(normal, conservative, proposal_source=source, needs_review=False)


def test_display_summaries_are_structural_and_not_raw_title_copy():
    observation = AIObservation(
        product_name="新品热卖柔性商品适用人群颜色列表", overall_form="flexible_chain", packing_actions=["coil"],
        display_packaging_summary="自封袋；盘绕收纳；仅防刮",
    )
    assert product_summary(observation) == "柔性商品；柔性链状；可盘绕"
    assert packaging_summary(observation, _proposal()) == "自封袋；盘绕收纳；仅防刮"


def test_reminder_uses_adopted_source_and_real_weight_risk_in_chinese():
    proposal = _proposal(confidence="low")
    proposal.normal.weight_g = None
    text = normal_reminder(AIObservation(display_packaging_summary="OPP袋；平折；无需缓冲"), proposal)
    assert "AI估算" in text
    assert "包装重量缺失" in text
    assert "ai_candidate" not in text


def test_merchant_reminder_does_not_claim_generic_fallback():
    text = normal_reminder(AIObservation(), _proposal("merchant_candidate"))
    assert "图片明确规格" in text
    assert "通用" not in text
