from profit_accounting_26.application.local_reestimate_service import LocalReestimateService


def test_patch_fields_include_compression_state():
    assert "compressibility" in LocalReestimateService.ALLOWED_PATCH_FIELDS
    assert "packaging_state_hint" in LocalReestimateService.ALLOWED_PATCH_FIELDS
    assert "has_rigid_parts" in LocalReestimateService.ALLOWED_PATCH_FIELDS


def test_context_keeps_original_and_edited_summary_channels():
    prompt = LocalReestimateService._context(
        original_summary="原始摘要", current_summary="当前摘要", original_observation={"product_name": "商品"},
        user_overrides={"weight_g": 100}, adopted_normal={"weight_g": 120},
        original_product_summary="原商品", current_product_summary="改后商品",
        original_packaging_summary="原包装", current_packaging_summary="改后包装",
        cal_summary=["CAL-001"], rejected_candidates={"ai_candidate": ["missing_weight"]},
        visual_evidence={"weight_g": {"raw_text": "100g"}},
    )
    for expected in ("原商品", "改后商品", "原包装", "改后包装", "CAL-001", "missing_weight", "100g"):
        assert expected in prompt
