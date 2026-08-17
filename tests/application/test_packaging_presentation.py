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
    result = product_summary(observation)
    assert len(result) > 0  # summary is non-empty
    assert packaging_summary(observation, _proposal()) == "盘绕收纳；单件包装待确认"


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


def test_bulk_carton_text_is_not_displayed_as_an_individual_carton():
    proposal = _proposal()
    proposal.normal.packaging_method = "500个/箱 纸箱"
    text = packaging_summary(AIObservation(), proposal)
    assert text == "轻度防护；单件包装待确认"
    assert "纸箱" not in text


def test_explicit_single_box_can_be_displayed_as_individual_package():
    proposal = _proposal()
    proposal.normal.packaging_method = "1个/盒"
    assert packaging_summary(AIObservation(), proposal) == "轻度防护；单件纸盒装"


def test_ambiguous_bag_summary_is_regenerated_as_a_valid_package_statement():
    observation = AIObservation(display_packaging_summary="预计；袋装")
    text = packaging_summary(observation, _proposal())
    assert text != "预计；袋装"
    assert "；" in text
    assert "单件包装待确认" in text or "预计" in text


def test_unshown_individual_package_is_marked_as_estimated_or_pending():
    text = packaging_summary(AIObservation(), _proposal())
    assert "预计" in text or "待确认" in text
    assert all(token not in text for token in ("20", "120", "ai_candidate", "CAL-"))


# ==================================================================
# 数量稳定显示（PR #40 最小 UI 修复：结构化 purchase_quantity 优先）
# ==================================================================


def _obs(**kwargs) -> AIObservation:
    base = dict(product_name="测试商品", display_product_summary="测试商品")
    base.update(kwargs)
    return AIObservation(**base)


def test_quantity_4_with_long_summary_shows_structured_quantity():
    """purchase_quantity=4、quantity_summary 超长 → 仍稳定显示“数量 ×4”。"""
    obs = _obs(
        quantity=4, quantity_source="page",
        quantity_summary="页面显示已选1款4双，总价15.2元，规格为均码，尺码可选",
    )
    assert product_summary(obs) == "测试商品｜数量 ×4"


def test_quantity_4_with_empty_summary_shows_structured_quantity():
    """purchase_quantity=4、quantity_summary 为空 → 仍显示“数量 ×4”。"""
    obs = _obs(quantity=4, quantity_source="page", quantity_summary="")
    assert product_summary(obs) == "测试商品｜数量 ×4"


def test_quantity_4_with_short_summary_shows_quantity_once():
    """purchase_quantity=4、quantity_summary 很短 → 数量稳定显示一次，不重复文本。"""
    obs = _obs(quantity=4, quantity_source="page", quantity_summary="4双")
    result = product_summary(obs)
    assert result == "测试商品｜数量 ×4"
    assert result.count("4") == 1


def test_quantity_none_falls_back_to_short_summary():
    """purchase_quantity 缺失（assumed/unknown）+ 短 quantity_summary → fallback 显示。"""
    obs = _obs(quantity=1, quantity_source="assumed/unknown", quantity_summary="4双")
    assert product_summary(obs) == "测试商品｜4双"


def test_quantity_none_with_empty_summary_shows_title_only():
    """purchase_quantity 缺失 + quantity_summary 为空 → 只显示商品名。"""
    obs = _obs(quantity=1, quantity_source="assumed/unknown", quantity_summary="")
    assert product_summary(obs) == "测试商品"


def test_quantity_1_confirmed_still_shows():
    """purchase_quantity=1（有来源）→ 显示“数量 ×1”，避免用户不知道按几个商品计算。"""
    obs = _obs(quantity=1, quantity_source="page", quantity_summary="1双")
    assert product_summary(obs) == "测试商品｜数量 ×1"


def test_quantity_summary_original_kept_in_history_and_manifest():
    """quantity_summary 原始长文本在解析/历史/manifest 中不被截断或修改（只改显示层）。"""
    from profit_accounting_26.application.calibration_export_service import _machine_ai_initial
    from profit_accounting_26.application.recognition_service import RecognitionService

    full = "页面显示已选1款4双，总价15.2元，规格为均码，尺码可选"
    payload = {
        "product_name": "测试商品",
        "observed": {
            "product_price_rmb": None, "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None},
            "bare_weight_g": None,
        },
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 9, "weight_g": 680, "state": "袋装"},
        "quantity": {"purchase_quantity": 4, "quantity_source": "page", "quantity_summary": full},
        "note": "",
    }
    obs, _proposal_out = RecognitionService._parse_v1_payload(payload, model="test")
    # 解析层：原始文本完整保留
    assert obs.quantity_summary == full
    # 历史层：layers.ai_raw.observation 原样包含完整文本（不改数据合同）
    record = {"_v2": {"ai_initial": {"observation": obs.to_dict()}}}
    assert record["_v2"]["ai_initial"]["observation"]["quantity_summary"] == full
    # manifest 层：machine_facts.ai_initial.observation.quantity_summary 完整
    initial = _machine_ai_initial(record)
    assert initial["observation"]["quantity_summary"] == full
    # 显示层：结构化数量优先，长文本不隐藏数量
    assert product_summary(obs) == "测试商品｜数量 ×4"
