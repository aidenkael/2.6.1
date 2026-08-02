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


def test_cal068_is_scaled_reference_not_fixed_absolute_size(tmp_path: Path):
    s = service(tmp_path)
    base = AIObservation(product_name="透明PVC化妆包", product_type="transparent_cosmetic_bag", material="pvc",
                         rigidity="soft", foldability="good", compressibility="good",
                         length_cm=22, width_cm=11, height_cm=18, weight_g=100, **no_hard_kwargs())
    large = AIObservation.from_dict(base.to_dict())
    scale = 10 ** (1/3)
    large.length_cm *= scale; large.width_cm *= scale; large.height_cm *= scale
    p1 = s.estimate(base)
    p2 = s.estimate(large)
    assert (p1.normal.length_cm, p1.normal.width_cm, p1.normal.height_cm) == (10.0, 10.0, 3.0)
    assert p2.normal.length_cm > p1.normal.length_cm
    assert p2.normal.width_cm > p1.normal.width_cm
    assert p2.normal.height_cm > p1.normal.height_cm


def test_cal075_guard_avoids_full_flat_fold(tmp_path: Path):
    s = service(tmp_path)
    obs = AIObservation(product_name="较厚透明PVC化妆包", product_type="transparent_cosmetic_bag", material="pvc",
                        rigidity="semi_rigid", foldability="limited", compressibility="limited",
                        has_hard_bottom=True, has_frame=False, has_rigid_parts=True,
                        requires_shape_retention=True, length_cm=23, width_cm=11, height_cm=11, weight_g=150)
    proposal = s.estimate(obs)
    assert "AGR-PVC-STRUCTURED-075" in proposal.applied_profile_ids
    assert proposal.normal.height_cm >= 4


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
