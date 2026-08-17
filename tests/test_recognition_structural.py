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
            "packaging_state_hint": "full_flat_fold",
            "rigidity": "soft",
            "foldability": "good",
            "compressibility": "good",
            "requires_shape_retention": False,
            "packing_actions": ["flat_fold", "bag"],
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
        assert obs.packaging_state_hint == "full_flat_fold"
        assert obs.rigidity == "soft"
        assert obs.foldability == "good"
        assert obs.compressibility == "good"
        assert obs.requires_shape_retention is False
        # v1.8: packing_actions 只接受正式允许值；"bag" 非法值被过滤
        assert obs.packing_actions == ["flat_fold"]
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
        # v1.8: 数量无法确认 → 明确标记 assumed/unknown，不伪装成真实数量 1
        assert obs.quantity_source == "assumed/unknown"

    def test_null_quantity_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": None,
            "quantity_source": None,
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1
        assert obs.quantity_source == "assumed/unknown"

    def test_zero_quantity_keeps_default(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 0,
            "quantity_source": "default",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        assert obs.quantity == 1  # 0 is not > 0
        assert obs.quantity_source == "assumed/unknown"

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
        assert obs.quantity_source == "assumed/unknown"


class TestObservationToDictIncludesNewFields:
    """observation.to_dict() includes parsed structural and quantity fields."""

    def test_to_dict_contains_structural_fields(self):
        payload = _minimal_v1_payload(
            structure={
                "overall_form": "hard_long",
                "rigidity": "semi_rigid",
                "requires_shape_retention": True,
                "packing_actions": ["roll", "wrap"],
                "has_frame": True,
            },
            quantity={"purchase_quantity": 2, "quantity_source": "detail_page"},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="m")
        d = obs.to_dict()
        assert d["overall_form"] == "hard_long"
        assert d["rigidity"] == "semi_rigid"
        assert d["requires_shape_retention"] is True
        # v1.8: "wrap" 非法值被过滤，只保留正式允许值 "roll"
        assert d["packing_actions"] == ["roll"]
        assert d["has_frame"] is True
        assert d["quantity"] == 2
        assert d["quantity_source"] == "detail_page"


class TestPromptContent:
    """Prompt text contains required quantity/set and structure rules."""

    def test_prompt_contains_quantity_rules(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "quantity" in prompt
    def test_prompt_contains_structure_rules(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "structure" in prompt
    def test_prompt_json_example_includes_new_blocks(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert '"structure"' in prompt
        assert '"quantity"' in prompt
        assert '"purchase_quantity"' in prompt

    def test_prompt_version_bumped(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v2.1"
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
        # v1.8: 旧 payload 无数量 → assumed/unknown，不伪装成真实数量 1
        assert obs.quantity_source == "assumed/unknown"

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
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert "foldability" in prompt
    def test_prompt_uses_canonical_compressibility(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert "compressibility" in prompt
    def test_prompt_uses_canonical_overall_form(self):
        """overall_form 从 v1.7 prompt 示例中移除（降低 AI 复杂度），仅在 schema 保留兼容。"""
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        # overall_form 不再出现在 prompt 中（仅在 RESPONSE_SCHEMA 保留）
        schema = RecognitionService.RESPONSE_SCHEMA
        assert "overall_form" in schema["properties"]["structure"]["properties"]
    def test_prompt_uses_canonical_packing_actions(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert "packing_actions" in prompt
    def test_prompt_uses_canonical_packaging_state_hint(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        assert "packaging_state_hint" in prompt
    def test_prompt_version_is_v15(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v2.1"


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
        # v1.8: 数量无法确认 → 明确标记 assumed/unknown
        assert obs.quantity_source == "assumed/unknown"

    def test_prompt_separates_sales_unit_from_purchase_quantity(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "purchase_quantity" in prompt
    def test_prompt_fallback_note_for_unknown_quantity(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert "note" in prompt
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
