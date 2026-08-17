"""Targeted tests for Recognition v1.6 simplification."""

from __future__ import annotations

import json
import pytest

from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.application.packaging_presentation import product_summary
from profit_accounting_26.domain.models import AIObservation


def _minimal_v1_payload(**overrides):
    base = {
        "product_name": "Abstract Widget Alpha",
        "observed": {
            "product_price_rmb": 29.9,
            "page_shipping_rmb": 5.0,
            "bare_dimensions_cm": {"length": 20, "width": 15, "height": 8},
            "bare_weight_g": 300,
        },
        "bare_estimate": {
            "length_cm": 20, "width_cm": 15, "height_cm": 8, "weight_g": 300,
        },
        "shipment": {
            "length_cm": 22, "width_cm": 17, "height_cm": 10, "weight_g": 350,
            "state": "foldable; bagged",
        },
        "note": "",
    }
    base.update(overrides)
    return base


class TestPromptSimplification:
    def test_prompt_no_category_examples(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        forbidden = [
            "\u889c\u5b50", "\u624b\u5957", "\u978b", "\u5e3d\u5b50",
            "\u8863\u670d", "\u88e4\u5b50", "\u73a9\u5177",
            "socks", "gloves", "shoes", "hat", "clothing", "toy",
        ]
        for cat in forbidden:
            assert cat not in prompt, f"Prompt must not contain category: {cat}"

    def test_prompt_shorter_than_v15(self):
        prompt = RecognitionService._prompt(1, include_json_shape=False)
        assert len(prompt) < 1500, f"Prompt too long: {len(prompt)} chars"

    def test_prompt_core_fields_present(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        for field in ("product_name", "product_price_rmb", "page_shipping_rmb",
                       "bare_dimensions_cm", "bare_weight_g", "shipment",
                       "quantity", "purchase_quantity", "quantity_summary",
                       "structure", "field_evidence", "note"):
            assert field in prompt, f"Core field missing: {field}"

    def test_prompt_version_bumped(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.9"


class TestQuantitySummary:
    def test_quantity_summary_parsed(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 2,
            "quantity_source": "detail_page",
            "quantity_summary": "2\u5355\u4f4d\uff08\u51716\u4ef6\uff09",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.quantity_summary == "2\u5355\u4f4d\uff08\u51716\u4ef6\uff09"
        assert obs.quantity == 2

    def test_quantity_summary_missing_keeps_default(self):
        payload = _minimal_v1_payload()
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.quantity_summary == ""

    def test_quantity_summary_invalid_type_ignored(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 1,
            "quantity_source": "default",
            "quantity_summary": 12345,
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.quantity_summary == ""

    def test_quantity_summary_in_observation_dict(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": 1,
            "quantity_source": "sku_text",
            "quantity_summary": "1\u5355\u4f4d\uff08\u51712\u4ef6\uff09",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        d = obs.to_dict()
        assert "quantity_summary" in d
        assert d["quantity_summary"] == "1\u5355\u4f4d\uff08\u51712\u4ef6\uff09"

    def test_old_record_without_quantity_summary_loads(self):
        old_data = {"product_name": "Legacy Item", "quantity": 1, "quantity_source": "default"}
        obs = AIObservation.from_dict(old_data)
        assert obs.product_name == "Legacy Item"
        assert obs.quantity_summary == ""


class TestProductSummaryDisplay:
    def test_summary_with_quantity(self):
        obs = AIObservation(
            product_name="Widget Beta",
            display_product_summary="Widget Beta",
            quantity_summary="1\u5355\u4f4d\uff08\u51712\u4ef6\uff09",
        )
        result = product_summary(obs)
        assert "WidgetBeta" in result or "Widget Beta" in result
        assert "1\u5355\u4f4d" in result

    def test_summary_without_quantity(self):
        obs = AIObservation(product_name="Simple Item", display_product_summary="Simple Item")
        result = product_summary(obs)
        assert result in ("SimpleItem", "Simple Item")

    def test_summary_readonly_contract(self):
        import pathlib
        calc_src = pathlib.Path("src/profit_accounting_26/ui/pages/calculation_page.py").read_text(encoding="utf-8")
        assert "self.product_summary._widget.setReadOnly(True)" in calc_src


class TestReestimateFullContext:
    def test_reestimate_context_includes_initial_ai(self):
        import pathlib
        calc_src = pathlib.Path("src/profit_accounting_26/ui/pages/calculation_page.py").read_text(encoding="utf-8")
        assert "initial_ai_observation" in calc_src
        assert "initial_ai_snapshot" in calc_src

    def test_local_reestimate_service_accepts_initial_ai(self):
        import inspect
        from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
        sig = inspect.signature(LocalReestimateService._context)
        params = list(sig.parameters.keys())
        assert "initial_ai_observation" in params


class TestPriorityAndSafety:
    def test_confirmed_facts_not_overridden(self):
        payload = _minimal_v1_payload(observed={
            "product_price_rmb": 50, "page_shipping_rmb": 10,
            "bare_dimensions_cm": {"length": 30, "width": 20, "height": 10},
            "bare_weight_g": 500,
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.length_cm == 30
        assert obs.weight_g == 500

    def test_quantity_null_when_unconfirmed(self):
        payload = _minimal_v1_payload(quantity={
            "purchase_quantity": None, "quantity_source": None,
            "quantity_summary": "\u8d2d\u4e70\u6570\u91cf\u672a\u786e\u8ba4",
        })
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.quantity == 1
        assert obs.quantity_summary == "\u8d2d\u4e70\u6570\u91cf\u672a\u786e\u8ba4"

    def test_initial_snapshot_preserved(self):
        payload = _minimal_v1_payload(
            quantity={"purchase_quantity": 3, "quantity_source": "sku_text", "quantity_summary": "3\u5355\u4f4d"},
            structure={"rigidity": "soft", "foldability": "good"},
        )
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        d = obs.to_dict()
        assert d["quantity_summary"] == "3\u5355\u4f4d"
        assert d["rigidity"] == "soft"
