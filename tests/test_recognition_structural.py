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
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.4"


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
