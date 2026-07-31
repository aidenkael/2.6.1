from profit_accounting_26.application.local_reestimate_service import LocalReestimateService


def test_patch_fields_include_compression_state():
    assert "compressibility" in LocalReestimateService.ALLOWED_PATCH_FIELDS
    assert "packaging_state_hint" in LocalReestimateService.ALLOWED_PATCH_FIELDS
    assert "has_rigid_parts" in LocalReestimateService.ALLOWED_PATCH_FIELDS
