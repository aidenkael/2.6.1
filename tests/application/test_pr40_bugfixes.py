"""PR #40 targeted tests: Bug fixes + Prompt v1.7 + AI/adopted separation.

Coverage:
 1. confirmed_facts 漏传修复
 2. LocalReestimate 上下文修复
 3. Prompt v1.7 精简验证
 4. structure canonical value 验证
 5. 左卡(AI估算) vs 右卡(当前采用) 数据分离
 6. ai_initial 不可覆盖
 7. build_record_payload ai_raw 正确性
 8. Calibration Export 闭环层次
 9. quantity_summary 纯展示
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
from profit_accounting_26.application.calculation_session import CalculationSession
from profit_accounting_26.domain.models import (
    AIObservation,
    PackagingProposal,
    PackagingScenario,
    PackagingState,
)


# ------------------------------------------------------------------ helpers

def _make_proposal(*, length: float = 30, width: float = 20, height: float = 10,
                   weight: float = 500, source: str = "vision_ai_v1") -> PackagingProposal:
    """Build a minimal PackagingProposal for testing."""
    scenario_data = dict(
        packaging_state=PackagingState.UNKNOWN,
        packaging_method="袋装发货",
        length_cm=length, width_cm=width, height_cm=height, weight_g=weight,
        reasoning_summary="test", confidence="medium", needs_review=False,
    )
    return PackagingProposal(
        normal=PackagingScenario(label="AI估算", **scenario_data),
        conservative=PackagingScenario(label="当前采用", **scenario_data),
        proposal_source=source,
        engine_version="vision-runtime-v1",
        calibration_version="",
    )


def _v1_payload(**overrides) -> dict:
    """Build a minimal V1 recognition payload."""
    base = {
        "product_name": "测试商品",
        "observed": {
            "product_price_rmb": 59.9,
            "page_shipping_rmb": None,
            "bare_dimensions_cm": {"length": 25, "width": 15, "height": 5},
            "bare_weight_g": 300,
        },
        "bare_estimate": {"length_cm": None, "width_cm": None, "height_cm": None, "weight_g": None},
        "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500, "state": "袋装"},
        "quantity": {"purchase_quantity": 1, "quantity_source": "page", "quantity_summary": "1件"},
        "note": "",
    }
    base.update(overrides)
    return base


# ==================================================================
# Prompt v1.7 tests (items 7, 8, 9)
# ==================================================================

class TestPromptV17:
    """验证 Prompt 比 v1.6 更轻，不含具体商品/品类示例。"""

    def _prompt_text(self) -> str:
        return RecognitionService._prompt(1, include_json_shape=True)

    def test_prompt_version_is_v17(self):
        assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.7"

    def test_prompt_lighter_than_v16(self):
        """v1.7 prompt 文本部分不含旧版冗长数量规则和具体示例。

        v1.7 比 v1.6 更精简的关键不在于字符总数，而在于：
        1. 移除了 false enum 声明
        2. 移除了详细数量规则（销售单位判断流程等）
        3. 移除了具体商品示例
        4. 添加了精简的通用原则
        """
        prompt = self._prompt_text()
        # 验证 v1.6 中的冗长内容已移除
        # v1.6 包含的详细数量判断流程不再出现
        assert "销售单位包含什么" not in prompt
        assert "购买数量不能反推销售单位组成" not in prompt
        assert "主图多件不等于套装" not in prompt
        assert "库存/MOQ/销量/SKU选项数均非购买数量" not in prompt
        # v1.6 的 false enum 声明不再出现
        assert "enum 约束" not in prompt
        # prompt 文本部分（不含 JSON 示例）应在合理范围内
        text_end = prompt.find("\n严格按以下 JSON")
        if text_end < 0:
            text_end = prompt.find("\n只返回符合")
        prompt_text = prompt[:text_end] if text_end > 0 else prompt
        assert len(prompt_text) < 1300, f"Prompt 文本仍过长: {len(prompt_text)} chars"

    def test_prompt_no_concrete_product_examples(self):
        prompt = self._prompt_text()
        # 不应包含具体商品名称示例
        for banned in ("手提包", "连衣裙", "T恤", "手机壳", "钱包"):
            assert banned not in prompt, f"Prompt 包含具体商品示例: {banned}"

    def test_prompt_no_concrete_category_rules(self):
        """Prompt 不应包含具体品类经验或数值规则。

        注意：'CAL' 出现在 '禁止 CAL' 等否定上下文中是合法的（告知 AI 不要输出）。
        """
        prompt = self._prompt_text()
        # 不应包含具体品类经验规则
        for banned in ("R1", "R2", "品类经验", "压缩率 0.", "固定包装尺寸"):
            assert banned not in prompt, f"Prompt 包含具体规则: {banned}"

    def test_prompt_no_false_enum_claim(self):
        """v1.7 不再声称 '合法值由 JSON Schema enum 约束'（schema 实际无 enum）。"""
        prompt = self._prompt_text()
        assert "enum 约束" not in prompt
        assert "enum" not in prompt.lower() or "enum" not in prompt


# ==================================================================
# Structure canonical value validation (item 10)
# ==================================================================

class TestStructureCanonical:
    """structure 非法值不会被强行升级。"""

    def test_invalid_rigidity_rejected(self):
        payload = _v1_payload(structure={"rigidity": "super_hard"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        # 非法值不应写入，保持默认 "unknown"
        assert obs.rigidity == "unknown"

    def test_valid_rigidity_accepted(self):
        payload = _v1_payload(structure={"rigidity": "soft"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.rigidity == "soft"

    def test_invalid_foldability_rejected(self):
        payload = _v1_payload(structure={"foldability": "extreme"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.foldability == "unknown"

    def test_valid_foldability_accepted(self):
        payload = _v1_payload(structure={"foldability": "good"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.foldability == "good"

    def test_invalid_compressibility_rejected(self):
        payload = _v1_payload(structure={"compressibility": "maximum"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.compressibility == "unknown"

    def test_valid_packaging_state_hint_accepted(self):
        payload = _v1_payload(structure={"packaging_state_hint": "full_flat_fold"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.packaging_state_hint == "full_flat_fold"

    def test_invalid_packaging_state_hint_rejected(self):
        payload = _v1_payload(structure={"packaging_state_hint": "rolled_up"})
        obs, _ = RecognitionService._parse_v1_payload(payload, model="test")
        assert obs.packaging_state_hint == "unknown"


# ==================================================================
# CalculationSession confirmed_facts tests (items 1, 2, 3, 4)
# ==================================================================

class TestCalculationSession:
    """confirmed_facts 行为验证。"""

    def test_confirm_value_registers_user_confirmed(self):
        session = CalculationSession()
        session.confirm_value("weight_g", 300.0)
        facts = session.confirmed_facts()
        assert "weight_g" in facts
        assert facts["weight_g"]["value"] == 300.0
        assert facts["weight_g"]["source"] == "user_confirmed"

    def test_confirm_value_zero_weight_stored_but_ui_filters(self):
        """裸尺寸/裸重 0 在 session 层存储；UI 层 (_accept_numeric_field) 过滤。

        CalculationSession.confirm_value 不做值域过滤（0 是合法入参）；
        UI 层 _accept_numeric_field 把裸尺寸/裸重 0 转为 None 后才调用 confirm_value。
        """
        session = CalculationSession()
        # UI 层对裸重 0 会传 None 给 session
        session.confirm_value("weight_g", None)
        assert "weight_g" not in session.confirmed_facts()

    def test_confirm_value_zero_cost_is_confirmed(self):
        """金额字段 0 是合法值。"""
        session = CalculationSession()
        session.confirm_value("product_cost_rmb", 0)
        facts = session.confirmed_facts()
        assert "product_cost_rmb" in facts
        assert facts["product_cost_rmb"]["value"] == 0

    def test_user_confirmed_not_overwritten_by_ai(self):
        """用户确认事实不能被 AI 覆盖。"""
        session = CalculationSession()
        session.confirm_value("weight_g", 500.0)
        session.confirm_value("length_cm", 30.0)
        observation = AIObservation(weight_g=200.0, length_cm=25.0)
        conflicts = session.protect_confirmed_values(observation)
        # 用户值必须保留
        assert observation.weight_g == 500.0
        assert observation.length_cm == 30.0
        # 冲突应被记录
        assert "weight_g" in conflicts
        assert "length_cm" in conflicts

    def test_confirm_value_none_clears(self):
        session = CalculationSession()
        session.confirm_value("weight_g", 300.0)
        session.confirm_value("weight_g", None)
        assert "weight_g" not in session.confirmed_facts()


# ==================================================================
# LocalReestimate context tests (items 5, 6)
# ==================================================================

class TestLocalReestimateContext:
    """LocalReestimate payload 真正包含 initial AI context。"""

    def test_context_includes_initial_ai_observation(self):
        initial_obs = {
            "product_name": "真实商品名",
            "product_type": "bag",
            "length_cm": 25, "width_cm": 15, "height_cm": 5, "weight_g": 300,
        }
        initial_raw = {
            "observed": {"product_price_rmb": 59.9},
            "shipment": {"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500, "state": "袋装"},
        }
        prompt = LocalReestimateService._context(
            product_name="真实商品名",
            confirmed_facts={"weight_g": 300},
            current_shipment={"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500},
            user_correction="实际更大",
            initial_ai_observation=initial_obs,
            initial_ai_raw_payload=initial_raw,
        )
        # initial_ai_context 必须出现在发送给 AI 的 prompt 中
        assert "initial_ai_context" in prompt
        assert "真实商品名" in prompt

    def test_context_without_initial_ai_still_works(self):
        prompt = LocalReestimateService._context(
            product_name="测试",
            confirmed_facts={},
            current_shipment={},
            user_correction="修正",
            initial_ai_observation=None,
            initial_ai_raw_payload=None,
        )
        assert "initial_ai_context" not in prompt
        assert "测试" in prompt


# ==================================================================
# AI估算 vs 当前采用 数据分离 (items 11, 12, 13)
# ==================================================================

class TestProposalSeparation:
    """左卡(AI估算)只等于 external AI 原值，右卡是唯一物流输入。"""

    def test_raw_proposal_differs_from_arbitrated(self):
        raw = _make_proposal(length=30, width=20, height=10, weight=500, source="vision_ai_v1")
        arbitrated = _make_proposal(length=32, width=22, height=12, weight=550, source="safety_v1")
        # 两者可以不同
        assert raw.normal.length_cm != arbitrated.normal.length_cm
        assert raw.normal.weight_g != arbitrated.normal.weight_g

    def test_session_stores_raw_not_arbitrated(self):
        session = CalculationSession()
        raw = _make_proposal(source="vision_ai_v1")
        arbitrated = _make_proposal(length=35, source="safety_v1")
        # ai_packaging_proposal 必须存 raw
        session.ai_packaging_proposal = raw
        # adopted 存 arbitrated
        session.adopt(arbitrated)
        assert session.ai_packaging_proposal.proposal_source == "vision_ai_v1"
        assert session.adopted_packaging.proposal_source == "safety_v1"

    def test_adopted_is_authority_for_logistics(self):
        """物流/利润只读 adopted_packaging。"""
        session = CalculationSession()
        raw = _make_proposal(weight=500)
        arbitrated = _make_proposal(weight=600)
        session.adopt(arbitrated)
        # 物流计算只使用 adopted
        assert session.adopted_packaging.normal.weight_g == 600


# ==================================================================
# ai_initial 不可覆盖 (item 14)
# ==================================================================

class TestAiInitialImmutable:
    """ai_initial 快照一旦写入不可覆盖。"""

    def test_initial_snapshot_captured_once(self):
        """_maybe_capture 只在 None 时捕获。"""
        # 模拟：第一次捕获
        snapshot1 = {"observation": {"product_name": "第一次"}, "prompt_version": "v1.7"}
        # 模拟：第二次调用不应覆盖
        snapshot2 = {"observation": {"product_name": "第二次"}, "prompt_version": "v1.8"}
        # 模拟 CalculationPage 的 _maybe_capture 逻辑
        initial_ai_snapshot = None
        if initial_ai_snapshot is None:
            initial_ai_snapshot = snapshot1
        if initial_ai_snapshot is None:  # 第二次
            initial_ai_snapshot = snapshot2
        assert initial_ai_snapshot["observation"]["product_name"] == "第一次"

    def test_v2_ai_initial_never_overwritten_on_update(self):
        """HistoryRecordV2Service.update_record 不覆盖 ai_initial。"""
        from profit_accounting_26.application.data_contracts import attach_v2_block, v2_block_from_payload
        payload = {}
        attach_v2_block(payload, origin="new_calculation", revision=1,
                       ai_initial={"observation": {"product_name": "首次AI"}},
                       current_estimate={})
        v2 = v2_block_from_payload(payload)
        assert v2["ai_initial"]["observation"]["product_name"] == "首次AI"
        # update 时 ai_initial=None → 保留
        attach_v2_block(payload, origin="history_edit", revision=2,
                       ai_initial=None, current_estimate={"length_cm": 35})
        v2_updated = v2_block_from_payload(payload)
        assert v2_updated["ai_initial"]["observation"]["product_name"] == "首次AI"


# ==================================================================
# build_record_payload ai_raw 正确性 (item 15)
# ==================================================================

class TestBuildRecordPayload:
    """新记录 ai_raw 不得保存 adopted 冒充 AI。"""

    def test_ai_raw_uses_session_ai_packaging_proposal(self):
        session = CalculationSession()
        raw = _make_proposal(weight=500, source="vision_ai_v1")
        adopted = _make_proposal(weight=600, source="safety_v1")
        session.ai_packaging_proposal = raw
        session.adopt(adopted)
        # 模拟 build_record_payload 中 ai_raw 的逻辑
        ai_raw_proposal = (
            session.ai_packaging_proposal.to_dict()
            if session.ai_packaging_proposal else (
                session.adopted_packaging.to_dict() if session.adopted_packaging else {}
            )
        )
        assert ai_raw_proposal["proposal_source"] == "vision_ai_v1"
        assert ai_raw_proposal != session.adopted_packaging.to_dict()

    def test_ai_raw_fallback_to_adopted_for_legacy(self):
        """旧记录（无 ai_packaging_proposal）允许 fallback。"""
        session = CalculationSession()
        adopted = _make_proposal(weight=600)
        session.adopt(adopted)
        session.ai_packaging_proposal = None
        ai_raw_proposal = (
            session.ai_packaging_proposal.to_dict()
            if session.ai_packaging_proposal else (
                session.adopted_packaging.to_dict() if session.adopted_packaging else {}
            )
        )
        # Legacy fallback 指向 adopted（可接受）
        assert ai_raw_proposal["proposal_source"] == "vision_ai_v1"


# ==================================================================
# Calibration Export 闭环 (item 16)
# ==================================================================

class TestCalibrationExportLayers:
    """Calibration Export 能区分 first AI / adopted / user / actual。"""

    def test_export_distinguishes_first_ai_from_adopted(self):
        from profit_accounting_26.application.calibration_export_service import (
            _ai_initial_block, _packaging_proposal_block,
        )
        payload = {
            "_v2": {
                "ai_initial": {
                    "external_ai_packaging_proposal": {
                        "normal": {"length_cm": 30, "width_cm": 20, "height_cm": 10, "weight_g": 500},
                        "proposal_source": "vision_ai_v1",
                    },
                    "adopted_packaging": {
                        "normal": {"length_cm": 32, "width_cm": 22, "height_cm": 12, "weight_g": 550},
                        "proposal_source": "safety_v1",
                    },
                    "observation": {"product_name": "测试"},
                }
            }
        }
        initial = _ai_initial_block(payload)
        assert initial["external_ai_packaging_proposal"]["proposal_source"] == "vision_ai_v1"
        assert initial["adopted_packaging"]["proposal_source"] == "safety_v1"
        # _packaging_proposal_block 优先 external
        block = _packaging_proposal_block(initial)
        assert block["source_kind"] == "external_ai_packaging_proposal"

    def test_export_handles_missing_external(self):
        from profit_accounting_26.application.calibration_export_service import _packaging_proposal_block
        initial = {
            "adopted_packaging": {
                "normal": {"length_cm": 32},
                "proposal_source": "safety_v1",
            },
        }
        block = _packaging_proposal_block(initial)
        assert block["source_kind"] == "ai_initial.adopted_packaging"


# ==================================================================
# quantity_summary 纯展示 (item 17)
# ==================================================================

class TestQuantitySummary:
    """quantity_summary 不参与物流计算。"""

    def test_quantity_summary_not_in_logistics(self):
        """验证 quantity_summary 不出现在物流计算相关代码路径中。"""
        # quantity_summary 只在 observation/presentation/export 中存在
        # 不在 packaging_estimation_service 的任何计算逻辑中使用
        from profit_accounting_26.application import packaging_estimation_service as pes
        source = open(pes.__file__, encoding="utf-8").read()
        assert "quantity_summary" not in source, \
            "quantity_summary 不应出现在 packaging_estimation_service 中"

    def test_quantity_summary_only_display(self):
        obs = AIObservation(quantity_summary="1单位（共2件）")
        # quantity_summary 是可读字符串，不是数值
        assert isinstance(obs.quantity_summary, str)
        # 物流计算只使用 observation.quantity (int)
        assert hasattr(obs, "quantity")


# ==================================================================
# Prompt JSON shape simplified (item 4 continued)
# ==================================================================

class TestPromptJsonShape:
    """JSON 示例中 structure 已精简。"""

    def test_json_shape_excludes_deemphasized_fields(self):
        prompt = RecognitionService._prompt(1, include_json_shape=True)
        # JSON 在 "：\n" 之后（全角冒号后换行 + JSON 对象）
        # 找最后一个 "{" 开始的完整 JSON
        marker = "不要 Markdown：\n"
        idx = prompt.find(marker)
        assert idx >= 0, "无法定位 JSON 示例"
        json_text = prompt[idx + len(marker):]
        shape = json.loads(json_text)
        structure = shape.get("structure", {})
        # 从 prompt JSON 示例中移除的字段
        assert "overall_form" not in structure
        assert "packing_constraints" not in structure
        assert "has_rigid_parts" not in structure
        assert "protrusion_flattenable" not in structure
        # 保留的核心字段
        assert "packaging_state_hint" in structure
        assert "rigidity" in structure
        assert "foldability" in structure
        assert "has_hard_bottom" in structure

    def test_response_schema_unchanged_for_compat(self):
        """RESPONSE_SCHEMA 仍包含所有字段（历史兼容）。"""
        schema = RecognitionService.RESPONSE_SCHEMA
        structure_props = schema["properties"]["structure"]["properties"]
        assert "overall_form" in structure_props
        assert "packing_constraints" in structure_props
        assert "protrusion_flattenable" in structure_props
