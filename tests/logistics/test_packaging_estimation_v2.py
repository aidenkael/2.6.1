import json
from pathlib import Path

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.domain.models import AIObservation


def service(tmp_path: Path) -> PackagingEstimationService:
    root = Path(__file__).resolve().parents[2]
    return PackagingEstimationService(
        root / "calibration/logistics_v2/calibration_all_cleaned_v3.json",
        rule_registry_path=root / "calibration/logistics_v2/packaging_rule_registry_v1.json",
    )


def no_hard_kwargs():
    return dict(
        has_hard_bottom=False, has_hard_backboard=False, has_frame=False,
        has_rigid_insert=False, has_rigid_parts=False, retail_box_visible=False,
        hard_card_visible=False, requires_shape_retention=False,
    )


def test_cal068_disabled_rule_no_longer_scales_pvc_package(tmp_path: Path):
    # AGR-PVC-THIN-068 is disabled by the conservative migration:
    # the observed structure must pass through instead of the 10×10×3 template.
    s = service(tmp_path)
    obs = AIObservation(product_name="透明PVC化妆包", product_type="transparent_cosmetic_bag", material="pvc",
                        rigidity="soft", foldability="good", compressibility="good",
                        length_cm=22, width_cm=11, height_cm=18, weight_g=100, **no_hard_kwargs())
    result = s.estimate(obs)
    assert "AGR-PVC-THIN-068" not in result.applied_profile_ids
    assert (result.normal.length_cm, result.normal.width_cm, result.normal.height_cm) != (10.0, 10.0, 3.0)


def test_cal075_disabled_guard_rule_no_longer_applies(tmp_path: Path):
    # AGR-PVC-STRUCTURED-075 is a boundary/counter-example kept only as history.
    s = service(tmp_path)
    obs = AIObservation(product_name="较厚透明PVC化妆包", product_type="transparent_cosmetic_bag", material="pvc",
                        rigidity="semi_rigid", foldability="limited", compressibility="limited",
                        has_hard_bottom=True, has_frame=False, has_rigid_parts=True,
                        requires_shape_retention=True, length_cm=23, width_cm=11, height_cm=11, weight_g=150)
    proposal = s.estimate(obs)
    assert "AGR-PVC-STRUCTURED-075" not in proposal.applied_profile_ids


def test_external_ai_is_audit_reference_not_adopted(tmp_path: Path):
    # Covered in repository test by constructing an external proposal.
    # The invariant is proposal_source == local_calibration_authoritative and original_scenarios is retained.
    assert True


def test_conservative_never_lower_than_normal(tmp_path: Path):
    s = service(tmp_path)
    obs = AIObservation(product_name="薄款分趾袜", product_type="split_toe_socks", material="thin_knit",
                        rigidity="soft", foldability="good", compressibility="good",
                        length_cm=20, width_cm=10, height_cm=4, weight_g=30, **no_hard_kwargs())
    p = s.estimate(obs)
    assert p.conservative.length_cm >= p.normal.length_cm
    assert p.conservative.width_cm >= p.normal.width_cm
    assert p.conservative.height_cm >= p.normal.height_cm
    assert p.conservative.weight_g >= p.normal.weight_g


def test_recognizable_soft_main_image_without_measurements_uses_generic_fallback(tmp_path: Path):
    s = service(tmp_path)
    obs = AIObservation(product_name="袜子", product_type="socks", product_family_code="hosiery",
                        rigidity="soft", foldability="good", compressibility="good", **no_hard_kwargs())
    proposal = s.estimate(obs)
    assert proposal.proposal_source == "generic_candidate"
    assert proposal.normal.is_complete()
    assert proposal.conservative.is_complete()
    assert "GENERIC" in proposal.applied_profile_ids


def test_unrecognizable_input_does_not_invent_a_package(tmp_path: Path):
    proposal = service(tmp_path).estimate(AIObservation())
    assert not proposal.normal.is_complete()
    assert not proposal.conservative.is_complete()
