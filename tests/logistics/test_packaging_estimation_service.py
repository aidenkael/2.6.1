from __future__ import annotations

import json
from pathlib import Path

from profit_accounting_26.application import PackagingEstimationService
from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)


def write_samples(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "CAL-X1",
                    "product_type": "soft_pouch",
                    "material": "pvc",
                    "rigidity": "soft",
                    "size_reduction_ratio": 0.5,
                    "usable_for_rule_learning": True,
                },
                {
                    "sample_id": "CAL-X2",
                    "product_type": "soft_pouch",
                    "material": "pvc",
                    "rigidity": "soft",
                    "size_reduction_ratio": 0.6,
                    "usable_for_rule_learning": True,
                },
            ]
        ),
        encoding="utf-8",
    )


def test_unknown_structure_is_not_treated_as_safe_compression(tmp_path: Path):
    samples = tmp_path / "samples.json"
    write_samples(samples)
    service = PackagingEstimationService(samples)
    observation = AIObservation(
        product_type="soft_pouch",
        material="pvc",
        rigidity="soft",
        foldability="good",
        length_cm=20,
        width_cm=10,
        height_cm=8,
        weight_g=100,
    )
    proposal = service.estimate(observation)
    assert proposal.normal.packaging_state is PackagingState.UNKNOWN
    assert proposal.needs_review
    assert any("硬结构字段未知" in reason for reason in proposal.review_reasons)


def test_explicit_no_hard_structure_allows_data_driven_candidate(tmp_path: Path):
    samples = tmp_path / "samples.json"
    write_samples(samples)
    service = PackagingEstimationService(samples)
    observation = AIObservation(
        product_type="soft_pouch",
        material="pvc",
        rigidity="soft",
        foldability="good",
        compressibility="good",
        has_hard_bottom=False,
        has_hard_backboard=False,
        has_frame=False,
        has_rigid_insert=False,
        has_rigid_parts=False,
        retail_box_visible=False,
        hard_card_visible=False,
        requires_shape_retention=False,
        length_cm=20,
        width_cm=10,
        height_cm=8,
        weight_g=100,
    )
    proposal = service.estimate(observation)
    assert proposal.normal.packaging_state is PackagingState.MODERATE_COMPRESSION
    assert set(proposal.applied_profile_ids) == {"CAL-X1", "CAL-X2"}
    assert proposal.normal.length_cm < 20
    assert proposal.normal.weight_g == 120


def test_external_ai_conflict_preserves_original_and_local(tmp_path: Path):
    samples = tmp_path / "samples.json"
    write_samples(samples)
    service = PackagingEstimationService(samples)
    observation = AIObservation(
        product_type="soft_pouch",
        material="pvc",
        rigidity="soft",
        foldability="good",
        has_hard_bottom=False,
        has_hard_backboard=False,
        has_frame=False,
        has_rigid_insert=False,
        has_rigid_parts=False,
        retail_box_visible=False,
        hard_card_visible=False,
        requires_shape_retention=False,
        length_cm=20,
        width_cm=10,
        height_cm=8,
        weight_g=100,
    )
    external = PackagingProposal(
        normal=PackagingScenario(
            label="正常档",
            packaging_state=PackagingState.MODERATE_COMPRESSION,
            packaging_method="AI袋装",
            length_cm=18,
            width_cm=9,
            height_cm=7,
            weight_g=140,
            needs_review=False,
        ),
        conservative=PackagingScenario(
            label="保守档",
            packaging_state=PackagingState.MODERATE_COMPRESSION,
            packaging_method="AI保守袋装",
            length_cm=19,
            width_cm=10,
            height_cm=8,
            weight_g=160,
            needs_review=False,
        ),
        proposal_source="external_ai",
        needs_review=False,
    )
    proposal = service.estimate(observation, external_proposal=external)
    assert proposal.normal.packaging_method == "AI袋装"
    assert proposal.original_scenarios["normal"]["packaging_method"] == "AI袋装"
    assert proposal.local_proposed_scenarios["normal"]["packaging_method"] != "AI袋装"
    assert proposal.adjusted_scenarios["normal"]["packaging_method"] == "AI袋装"
    assert proposal.conflicts
    assert proposal.needs_review


def test_soft_item_without_matching_samples_is_not_auto_compressed(tmp_path: Path):
    samples = tmp_path / "samples.json"
    samples.write_text("[]", encoding="utf-8")
    service = PackagingEstimationService(samples)
    observation = AIObservation(
        product_type="unknown_soft_item",
        material="unknown",
        rigidity="soft",
        foldability="good",
        compressibility="good",
        has_hard_bottom=False,
        has_hard_backboard=False,
        has_frame=False,
        has_rigid_insert=False,
        has_rigid_parts=False,
        retail_box_visible=False,
        hard_card_visible=False,
        requires_shape_retention=False,
        length_cm=20,
        width_cm=10,
        height_cm=8,
        weight_g=100,
    )
    proposal = service.estimate(observation)
    assert proposal.normal.length_cm == 20
    assert proposal.normal.needs_review
    assert "未自动压缩尺寸" in "；".join(proposal.review_reasons)
