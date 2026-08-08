"""Regenerate the SYNTHETIC mechanism-regression fixtures.

These cases are fictional products with fictional AI responses. They exist
only to regression-test evaluation harness mechanics (replay layers, scoring
plumbing, CLI). They MUST NOT be counted as real accuracy evidence.

Run from the repository root:

    python tests/evaluation/vision_packaging/synthetic/generate_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_VERSION = "vision-packaging-eval-case-v1"


def _provider_response(payload: dict, response_id: str) -> dict:
    return {
        "id": response_id,
        "object": "chat.completion",
        "model": "synthetic-fixture-v1",
        "choices": [
            {"index": 0, "finish_reason": "stop",
             "message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}},
        ],
        "usage": {"prompt_tokens": 128, "completion_tokens": 256, "total_tokens": 384},
    }


def _structure_evidence() -> dict:
    empty = {"source_image_index": None, "raw_text": "", "region_description": "", "confidence": "low"}
    return {name: dict(empty) for name in (
        "has_hard_bottom", "has_hard_backboard", "has_frame", "has_rigid_insert",
        "has_rigid_parts", "retail_box_visible", "hard_card_visible",
    )}


def syn_01_payload() -> dict:
    """Hard flat item, complete AI candidate, adopted unchanged by baseline."""
    return {
        "observation": {
            "product_name": "亚克力杯垫", "product_type": "杯垫", "product_family": "家居小件",
            "product_type_raw": "亚克力杯垫", "product_type_code": "unknown", "product_family_code": "unknown",
            "material": "亚克力", "material_family": "塑料", "material_family_code": "unknown",
            "display_product_summary": "圆形亚克力杯垫一件", "display_packaging_summary": "未见零售包装",
            "overall_form": "hard_flat", "packing_actions": [], "packing_constraints": [],
            "rigidity": "hard", "foldability": "none", "compressibility": "none",
            "packaging_state_hint": "moderate_compression", "requires_shape_retention": False,
            "has_hard_bottom": False, "has_hard_backboard": False, "has_frame": False,
            "has_rigid_insert": False, "has_rigid_parts": False, "retail_box_visible": False,
            "hard_card_visible": False, "protrusion_flattenable": False,
            "product_cost_rmb": 3.5, "product_cost_value_type": "exact",
            "domestic_shipping_rmb": 0, "domestic_shipping_value_type": "exact",
            "length_cm": 12, "width_cm": 10, "height_cm": 1.5, "weight_g": 80,
            "dimension_value_source": "image_text", "weight_value_source": "image_text",
            "dimension_scope": "product_size", "weight_scope": "net_weight",
            "quantity": 1, "confidence": "high",
        },
        "field_evidence": {
            "product_cost_rmb": {"source_image_index": 0, "raw_text": "3.5元", "confidence": "high"},
            "domestic_shipping_rmb": {"source_image_index": 0, "raw_text": "包邮", "confidence": "medium"},
            "dimensions": {"source_image_index": 1, "raw_text": "12x10x1.5cm", "meaning": "单件外廓",
                            "semantic_note": "", "confidence": "high"},
            "weight": {"source_image_index": 1, "raw_text": "80g", "confidence": "high"},
            "structure": _structure_evidence(),
            "transport_outline": {"source_image_index": None, "raw_text": "", "visible_features": [],
                                    "region_description": "", "confidence": "low"},
        },
        "packaging_proposal": {
            "normal": {"label": "正常档", "packaging_state": "moderate_compression",
                        "packaging_method": "气泡袋+纸卡", "length_cm": 13, "width_cm": 11,
                        "height_cm": 2.5, "weight_g": 100, "reasoning_summary": "硬质薄片加气泡袋",
                        "confidence": "high", "needs_review": False},
            "conservative": {"label": "保守档", "packaging_state": "moderate_compression",
                              "packaging_method": "气泡袋+硬纸板", "length_cm": 14, "width_cm": 12,
                              "height_cm": 3.5, "weight_g": 115, "reasoning_summary": "保守加护",
                              "confidence": "medium", "needs_review": False},
            "proposal_source": "vision_api", "needs_review": False, "review_reasons": [],
        },
    }


def syn_02_payload() -> dict:
    """Adjustable-length leash: dimension semantic issue rejects AI candidate; salvage path."""
    return {
        "observation": {
            "product_name": "宠物牵引绳", "product_type": "牵引绳", "product_family": "宠物用品",
            "product_type_raw": "宠物牵引绳", "product_type_code": "unknown", "product_family_code": "unknown",
            "material": "尼龙", "material_family": "织物", "material_family_code": "unknown",
            "display_product_summary": "尼龙宠物牵引绳一条", "display_packaging_summary": "未见包装",
            "overall_form": "flexible_chain", "packing_actions": ["coil"], "packing_constraints": [],
            "rigidity": "soft", "foldability": "good", "compressibility": "unknown",
            "packaging_state_hint": "moderate_compression", "requires_shape_retention": False,
            "has_hard_bottom": False, "has_hard_backboard": False, "has_frame": False,
            "has_rigid_insert": False, "has_rigid_parts": False, "retail_box_visible": False,
            "hard_card_visible": False, "protrusion_flattenable": None,
            "product_cost_rmb": 8.9, "product_cost_value_type": "exact",
            "domestic_shipping_rmb": 2, "domestic_shipping_value_type": "exact",
            "length_cm": None, "width_cm": None, "height_cm": None, "weight_g": 120,
            "dimension_value_source": "image_text", "weight_value_source": "image_text",
            "dimension_scope": "adjustable_range", "weight_scope": "net_weight",
            "quantity": 1, "confidence": "medium",
        },
        "field_evidence": {
            "product_cost_rmb": {"source_image_index": 0, "raw_text": "8.9元", "confidence": "high"},
            "domestic_shipping_rmb": {"source_image_index": 0, "raw_text": "运费2元", "confidence": "high"},
            "dimensions": {"source_image_index": 1, "raw_text": "长度 100-120cm 可调节",
                            "meaning": "可调长度范围", "semantic_note": "非单件三维外廓", "confidence": "high"},
            "weight": {"source_image_index": 1, "raw_text": "120g", "confidence": "high"},
            "structure": _structure_evidence(),
            "transport_outline": {"source_image_index": None, "raw_text": "", "visible_features": [],
                                    "region_description": "", "confidence": "low"},
        },
        "packaging_proposal": {
            "normal": {"label": "正常档", "packaging_state": "moderate_compression",
                        "packaging_method": "盘绕后袋装", "length_cm": 18, "width_cm": 12,
                        "height_cm": 4, "weight_g": 150, "reasoning_summary": "盘绕后装袋",
                        "confidence": "medium", "needs_review": False},
            "conservative": {"label": "保守档", "packaging_state": "moderate_compression",
                              "packaging_method": "盘绕后袋装加厚", "length_cm": 20, "width_cm": 14,
                              "height_cm": 5, "weight_g": 170, "reasoning_summary": "保守加护",
                              "confidence": "medium", "needs_review": False},
            "proposal_source": "vision_api", "needs_review": False, "review_reasons": [],
        },
    }


def syn_03_payload() -> dict:
    """Merchant shipping-package facts override everything (deterministic path)."""
    return {
        "observation": {
            "product_name": "玻璃水杯", "product_type": "水杯", "product_family": "杯具",
            "product_type_raw": "玻璃水杯", "product_type_code": "unknown", "product_family_code": "unknown",
            "material": "玻璃", "material_family": "玻璃", "material_family_code": "unknown",
            "display_product_summary": "玻璃水杯一只", "display_packaging_summary": "商家展示运输包装",
            "overall_form": "hard_3d", "packing_actions": [], "packing_constraints": ["do_not_compress"],
            "rigidity": "hard", "foldability": "none", "compressibility": "none",
            "packaging_state_hint": "moderate_compression", "requires_shape_retention": False,
            "has_hard_bottom": False, "has_hard_backboard": False, "has_frame": False,
            "has_rigid_insert": False, "has_rigid_parts": False, "retail_box_visible": False,
            "hard_card_visible": False, "protrusion_flattenable": False,
            "product_cost_rmb": 12, "product_cost_value_type": "exact",
            "domestic_shipping_rmb": 5, "domestic_shipping_value_type": "exact",
            "length_cm": 20, "width_cm": 15, "height_cm": 8, "weight_g": 350,
            "dimension_value_source": "image_text", "weight_value_source": "image_text",
            "dimension_scope": "shipping_package_size", "weight_scope": "packaged_weight",
            "quantity": 1, "confidence": "high",
        },
        "field_evidence": {
            "product_cost_rmb": {"source_image_index": 0, "raw_text": "12元", "confidence": "high"},
            "domestic_shipping_rmb": {"source_image_index": 0, "raw_text": "运费5元", "confidence": "high"},
            "dimensions": {"source_image_index": 1, "raw_text": "20x15x8cm 单件运输包装",
                            "meaning": "运输包装外廓", "semantic_note": "", "confidence": "high"},
            "weight": {"source_image_index": 1, "raw_text": "含包装350g", "confidence": "high"},
            "structure": _structure_evidence(),
            "transport_outline": {"source_image_index": 1, "raw_text": "运输包装实拍",
                                    "visible_features": ["纸箱"], "region_description": "整体",
                                    "confidence": "high"},
        },
        "packaging_proposal": {
            "normal": {"label": "正常档", "packaging_state": "moderate_compression",
                        "packaging_method": "运输纸箱", "length_cm": 21, "width_cm": 16,
                        "height_cm": 9, "weight_g": 380, "reasoning_summary": "按运输包装略放宽",
                        "confidence": "high", "needs_review": False},
            "conservative": {"label": "保守档", "packaging_state": "moderate_compression",
                              "packaging_method": "运输纸箱加护", "length_cm": 23, "width_cm": 18,
                              "height_cm": 10, "weight_g": 400, "reasoning_summary": "保守加护",
                              "confidence": "medium", "needs_review": False},
            "proposal_source": "vision_api", "needs_review": False, "review_reasons": [],
        },
    }


FIXTURES = {
    "syn_01_acrylic_coaster": {
        "payload": syn_01_payload,
        "description": "机制回归：硬质薄片，AI 完整候选被基线原样采纳（ai_candidate）。",
        "ground_truth": {
            "expected_product_summary": "亚克力杯垫",
            "expected_material": "亚克力",
            "expected_structure": "硬质薄片，无折叠能力",
            "bare_dimensions": {"value": {"length_cm": 12, "width_cm": 10, "height_cm": 1.5},
                                  "acceptable_range": {"length_cm": [11, 13], "width_cm": [9, 11],
                                                        "height_cm": [1, 2]}, "unknown": False},
            "bare_weight": {"value": 80, "acceptable_range": [60, 100], "unknown": False},
            "normal_packaging": {"length_range": [12, 14], "width_range": [10, 12],
                                   "height_range": [2, 3], "weight_range": [90, 120],
                                   "acceptable_methods": ["气泡袋", "袋装"]},
            "notes": "虚构案例，仅用于评测框架机制回归，不计入真实准确率。",
        },
    },
    "syn_02_adjustable_leash": {
        "payload": syn_02_payload,
        "description": "机制回归：可调长度语义问题否决 AI 候选后走 salvage（ai_candidate_salvaged）。",
        "ground_truth": {
            "expected_product_summary": "宠物牵引绳",
            "expected_material": "尼龙",
            "expected_structure": "柔性绳带，可盘绕",
            "bare_dimensions": {"unknown": True},
            "bare_weight": {"value": 120, "acceptable_range": [100, 140], "unknown": False},
            "normal_packaging": {"length_range": [16, 20], "width_range": [10, 14],
                                   "height_range": [3, 5], "weight_range": [130, 180],
                                   "acceptable_methods": ["袋装"]},
            "notes": "虚构案例；人工标准按 AI 独立包装候选设定，用于演示 post_ai_degradation 计算。",
        },
    },
    "syn_03_merchant_shipping_facts": {
        "payload": syn_03_payload,
        "description": "机制回归：商家运输包装事实优先（merchant_candidate）。",
        "ground_truth": {
            "expected_product_summary": "玻璃水杯",
            "expected_material": "玻璃",
            "expected_structure": "刚性杯体，不可压缩",
            "bare_dimensions": {"unknown": True},
            "bare_weight": {"unknown": True},
            "normal_packaging": {"length_range": [19, 21], "width_range": [14, 16],
                                   "height_range": [7, 9], "weight_range": [320, 380],
                                   "acceptable_methods": ["verified shipping package"]},
            "notes": "虚构案例，仅用于评测框架机制回归。",
        },
    },
}


def generate() -> None:
    for case_id, spec in FIXTURES.items():
        case_dir = HERE / case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        response = _provider_response(spec["payload"](), f"chatcmpl-{case_id}")
        (case_dir / "ai_raw_response.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        metadata = {
            "case_id": case_id,
            "schema_version": SCHEMA_VERSION,
            "origin": "synthetic",
            "model": "synthetic-fixture-v1",
            "description": spec["description"],
            "images": [],
            "image_role_note": "synthetic 案例无图片；真实案例在此按张标注 main/dimension/weight/packaging/other",
            "current_observation": None,
            "current_packaging_result": None,
            "ground_truth": spec["ground_truth"],
        }
        (case_dir / "case.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"generated {case_dir}")


if __name__ == "__main__":
    generate()
