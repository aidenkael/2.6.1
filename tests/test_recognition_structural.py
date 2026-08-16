"""Targeted tests for RecognitionService structural + quantity field activation (v1.4).

No real API calls. Only exercises _parse_v1_payload and prompt content.
"""

from __future__ import annotations

import pytest

from profit_accounting_26.application.recognition_service import RecognitionService


def _minimal_v1_payload(**overrides):
    """Build a minimal valid V1 payload with optional structure/quantity overrides."""
    base = {
        "product_name": "Test Widget",
        "observed": {
            "product_price_rmb": None,
            "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": None, "width": None, "height": None},
            "bare_weight_g": None,
        },
        "bare_estimate": {
            "length_cm": 10,
            "width_cm": 8,
            "height_cm": 5,
            "weight_g": 200,
        },
        "shipment": {
            "length_cm": 12,
            "width_cm": 10,
            "height_cm": 6,
            "weight_g": 250,
            "state": "folded; bagged",
        },
        "note": "",
    }
    base.update(overrides)
    return base


class TestStructuralFieldParsing:
    """New structure fields map correctly into AIObservation."""

    def test_full_structure_fields_parsed(self):
        payload = _minimal_v1_payload(structure={
            "overall_form": "soft_flat",
            "packaging_state_hint": "folded",
            "rigidity": "flexible",
            "foldability": "flat_fold",
            "compressibility": "high",
            "requires_shape_retention": False,
            "packing_actions": ["fold", "bag"],
            "packing_constraints": ["do_not_bend"],
            "has_hard_bottom": False,
            "has_hard_backboard": False,
            "has_frame": False,
            "has_rigid_insert": False,
            "has_rigid_parts": False,
            "retail_box_visible": False,
            "hard_card_visible": False,
            "protrusion_flattenable": True,
        })
        obs, proposal = RecognitionService._parse_v1_payload(payload, model="test-model")
        assert obs.overall_form == "soft_flat"
        assert obs.packaging_state_hint == "folded"
        assert obs.rigidity == "flexible"
        assert obs.foldability == "flat_fold"
        assert obs.compressibility == "high"
        assert obs.requires_shape_retention is False
        assert obs.packing_actions == ["fold", "bag"]
        assert obs.packing_constraints == ["do_not_bend"]
        assert obs.has_hard_bottom is False
        assert obs.protrusion_flattenable is True

    def test_missing_structure_keeps_defaults(self):
        payload = _minimal_v1_payload()
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.overall_form == "unknown"
        assert obs.packaging_state_hint == "unknown"
        assert obs.rigidity == "unknown"
        assert obs.foldability == "unknown"
        assert obs.compressibility == "unknown"
        assert obs.requires_shape_retention is None
        assert obs.packing_actions == []
        assert obs.packing_constraints == []
        assert obs.has_hard_bottom is None
        assert obs.retail_box_visible is None

    def test_invalid_structure_values_do_not_crash(self):
        payload = _minimal_v1_payload(structure={
            "overall_form": 12345,
            "rigidity": None,
            "requires_shape_retention": "yes",
            "packing_actions": "not_a_list",
            "packing_constraints": [42, None, "keep_upright"],
            "has_hard_bottom": "true",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        # Invalid types should be ignored; defaults preserved
        assert obs.overall_form == "unknown"
        assert obs.rigidity == "unknown"
        assert obs.requires_shape_retention is None
        assert obs.packing_actions == []
        # Mixed list: only valid strings kept
        assert obs.packing_constraints == ["keep_upright"]
        assert obs.has_hard_bottom is None

    def test_empty_structure_dict_keeps_defaults(self):
        payload = _minimal_v1_payload(structure={})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.overall_form == "unknown"
        assert obs.packing_actions == []


class TestQuantityFieldParsing:
    """Quantity block maps to observation.quantity / quantity_source."""

    def test_valid_quantity_parsed(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 3,
            "quantity_source": "sku_text",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 3
        assert obs.quantity_source == "sku_text"

    def test_missing_quantity_keeps_default(self):
        payload = _minimal_v1_payload()
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1
        assert obs.quantity_source == "unknown"

    def test_null_quantity_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": None,
            "quantity_source": None,
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1
        assert obs.quantity_source == "unknown"

    def test_zero_quantity_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 0,
            "quantity_source": "default",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1  # 0 is not > 0
        assert obs.quantity_source == "default"

    def test_negative_quantity_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": -2,
            "quantity_source": "detail_page",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1

    def test_float_quantity_converts_to_int(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 2.0,
            "quantity_source": "packaging_label",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 2
        assert isinstance(obs.quantity, int)

    def test_invalid_quantity_type_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": "three",
            "quantity_source": 42,
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1
        assert obs.quantity_source == "unknown"


class TestObservationToDictIncludesNewFields:
    """observation.to_dict() includes parsed structural and quantity fields."""

    def test_to_dict_contains_structural_fields(self):
        payload = _minimal_v1_payload(
            structure={
                "overall_form": "rolled",
                "rigidity": "semi_rigid",
                "requires_shape_retention": True,
                "packing_actions": ["roll", "wrap"],
                "has_frame": True,
            },
            quantity={"purchase_quantity": 2, "quantity_source": "detail_page"},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        d = obs.to_dict()
        assert d["overall_form"] == "rolled"
        assert d["rigidity"] == "semi_rigid"
        assert d["requires_shape_retention"] is True
        assert d["packing_actions"] == ["roll", "wrap"]
        assert d["has_frame"] is True
        assert d["quantity"] == 2
        assert d["quantity_source"] == "detail_page"


class TestPromptContent:
    """Prompt text contains required quantity/set and structure rules."""

    def test_prompt_contains_quantity_rules(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "数量与套装判定" in prompt
        assert "不能仅凭图片数量自动认定为 N 件套" in prompt
        assert "不能因为文字没有明确写 N 件套就自动认定为单件展示" in prompt
        assert "禁止把单件 L/W/H 分别机械乘以数量" in prompt
        assert "不凭经验猜具体件数" in prompt
        assert "SKU/规格文字" in prompt
        assert "purchase_quantity" in prompt
        assert "quantity_source" in prompt

    def test_prompt_contains_structure_rules(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "structure" in prompt
        assert "展示状态不等于运输状态" in prompt
        assert "不要为了" in prompt or "不要为填满字段而猜测" in prompt
        assert "overall_form" in prompt
        assert "requires_shape_retention" in prompt
        assert "packing_actions" in prompt

    def test_prompt_json_example_includes_new_blocks(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert '"structure"' in prompt
        assert '"quantity"' in prompt
        assert '"purchase_quantity"' in prompt

    def test_prompt_version_bumped(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.5"


class TestBackwardCompatibility:
    """Old payloads without structure/quantity still work unchanged."""

    def test_old_payload_no_structure_no_quantity(self):
        payload = _minimal_v1_payload()
        obs, proposal = RecognitionService._parse_v1_payload(payload, model="old-model")
        assert obs.product_name == "Test Widget"
        assert obs.source == "vision_api"
        assert obs.model == "old-model"
        assert obs.prompt_version == RecognitionService.PROMPT_VERSION
        assert proposal is not None
        # Defaults intact
        assert obs.overall_form == "unknown"
        assert obs.quantity == 1
        assert obs.quantity_source == "unknown"

    def test_structure_non_dict_ignored(self):
        payload = _minimal_v1_payload(structure="not_a_dict")
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.overall_form == "unknown"

    def test_quantity_non_dict_ignored(self):
        payload = _minimal_v1_payload(quantity=[1, 2, 3])
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1


class TestCanonicalVocabulary:
    """Prompt specifies canonical values matching PackagingEstimationService."""

    def test_prompt_uses_canonical_foldability(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "good / limited / none / unknown" in prompt

    def test_prompt_uses_canonical_compressibility(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        # compressibility uses same set as foldability
        lines = prompt.split("\n")
        comp_line = [l for l in lines if "compressibility" in l and "仅限" in l]
        assert len(comp_line) == 1
        assert "good / limited / none / unknown" in comp_line[0]

    def test_prompt_uses_canonical_overall_form(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "soft_flat / hard_flat / flexible_chain" in prompt

    def test_prompt_uses_canonical_packing_actions(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "flat_fold / roll / coil / compress / nest / disassemble" in prompt

    def test_prompt_uses_canonical_packaging_state_hint(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "full_flat_fold / strong_compression / moderate_compression / shape_retained" in prompt

    def test_prompt_version_is_v15(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.5"


class TestFieldEvidence:
    """field_evidence is preserved in raw_payload and supports engine contract."""

    def test_field_evidence_preserved_in_raw_payload(self):
        payload = _minimal_v1_payload(
            structure={"has_hard_bottom": True},
            field_evidence={
                "has_hard_bottom": {
                    "source_image_index": 0,
                    "region_description": "bottom panel visible in photo",
                    "source": "image",
                }
            },
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        fe = obs.raw_payload.get("field_evidence", {})
        assert "has_hard_bottom" in fe
        assert fe["has_hard_bottom"]["source_image_index"] == 0
        assert fe["has_hard_bottom"]["source"] == "image"

    def test_field_evidence_absent_when_not_provided(self):
        payload = _minimal_v1_payload(structure={"has_hard_bottom": True})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.has_hard_bottom is True
        assert "field_evidence" not in obs.raw_payload or obs.raw_payload.get("field_evidence") is None or obs.raw_payload.get("field_evidence") == {}

    def test_field_evidence_non_dict_ignored(self):
        payload = _minimal_v1_payload(field_evidence="not_a_dict")
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        # Non-dict field_evidence is not processed into structured evidence;
        # the raw payload may still contain the original value from the input payload.
        fe = obs.raw_payload.get("field_evidence")
        assert not isinstance(fe, dict) or fe == {}

    def test_engine_recognizes_hard_with_evidence(self):
        """PackagingEstimationService._has_explicit_rigid_evidence returns True when
        hard boolean=True AND field_evidence has located entry."""
        from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
        svc = PackagingEstimationService()
        payload = _minimal_v1_payload(
            structure={"has_hard_bottom": True},
            field_evidence={
                "has_hard_bottom": {
                    "source_image_index": 0,
                    "region_description": "hard bottom panel",
                    "source": "image",
                }
            },
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert svc._has_explicit_rigid_evidence(obs) is True

    def test_engine_rejects_hard_without_evidence(self):
        """PackagingEstimationService._has_explicit_rigid_evidence returns False when
        hard boolean=True but no field_evidence."""
        from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
        svc = PackagingEstimationService()
        payload = _minimal_v1_payload(structure={"has_hard_bottom": True})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.has_hard_bottom is True
        assert svc._has_explicit_rigid_evidence(obs) is False


class TestQuantitySeparation:
    """purchase_quantity and sales-unit composition are fully separated."""

    def test_quantity_null_when_unconfirmed(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": None,
            "quantity_source": "default",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1  # default
        assert obs.quantity_source == "default"

    def test_prompt_separates_sales_unit_from_purchase_quantity(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "第一步" in prompt
        assert "第二步" in prompt
        assert '"当前购买数量"不能用于反推一个销售单位包含几件' in prompt

    def test_prompt_fallback_note_for_unknown_quantity(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "购买数量未确认，按1个销售单位估算" in prompt


class TestRawPayloadObservationSnapshot:
    """raw_payload['observation'] includes structure and quantity fields after mapping."""

    def test_raw_payload_observation_contains_structure(self):
        payload = _minimal_v1_payload(
            structure={"overall_form": "soft_flat", "foldability": "good"},
            quantity={"purchase_quantity": 3, "quantity_source": "sku_text"},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        rp_obs = obs.raw_payload.get("observation", {})
        assert rp_obs.get("overall_form") == "soft_flat"
        assert rp_obs.get("foldability") == "good"
        assert rp_obs.get("quantity") == 3
        assert rp_obs.get("quantity_source") == "sku_text"

    def test_raw_payload_observation_matches_to_dict(self):
        payload = _minimal_v1_payload(
            structure={"rigidity": "soft", "compressibility": "good"},
            quantity={"purchase_quantity": 2, "quantity_source": "detail_page"},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        d = obs.to_dict()
        rp_obs = obs.raw_payload.get("observation", {})
        for key in ("rigidity", "compressibility", "quantity", "quantity_source"):
            assert rp_obs.get(key) == d[key], f"{key} mismatch: raw_payload={rp_obs.get(key)} vs to_dict={d[key]}"
