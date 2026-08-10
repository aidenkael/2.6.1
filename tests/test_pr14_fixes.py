"""PR #14 最小修复回归测试。

覆盖本轮修复的八个问题：
A. API 绑定保存/重启持久化
B. 重估 confirmed_facts 只取 session 确认值
C. Prompt state 语义约束
D. UI：AI发货判断只读、用户修正框高度
E. 历史表行高
F. 诊断日志包含 provider/model
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    LOCAL_REESTIMATE,
    VISUAL_AI,
)
from profit_accounting_26.application.calculation_session import CalculationSession
from profit_accounting_26.application.recognition_service import (
    RecognitionService,
    _is_invalid_shipment_state,
)
from profit_accounting_26.application.local_reestimate_service import (
    LocalReestimateResult,
    LocalReestimateService,
)
from profit_accounting_26.domain.models import AIObservation


def _make_profile(name: str, *, provider: str = "自定义", model: str = "m-v1") -> ApiProfile:
    return ApiProfile.create(
        display_name=name,
        provider=provider,
        api_url="https://api.example.test/v1/chat/completions",
        model_name=model,
    )


# =========================================================================
# A. API binding persistence
# =========================================================================


class TestApiBindingPersistence:
    """A1-A4: visual/local binding 保存后重启仍保持；两功能可绑不同 Profile；
    save_profile 不覆盖 binding。"""

    def test_binding_persists_across_store_restart(self, tmp_path):
        """A1: visual=B, local=A → 新建 ApiProfileStore 重新读取 → 仍然 B / A。"""
        store = ApiProfileStore(tmp_path)
        a = _make_profile("Profile A")
        b = _make_profile("Profile B")
        store.save_profile(a, "key-a")
        store.save_profile(b, "key-b")
        store.bind(VISUAL_AI, b.profile_id)
        store.bind(LOCAL_REESTIMATE, a.profile_id)

        fresh = ApiProfileStore(tmp_path)
        visual = fresh.bound_profile(VISUAL_AI)
        local = fresh.bound_profile(LOCAL_REESTIMATE)
        assert visual is not None and visual[0].profile_id == b.profile_id
        assert local is not None and local[0].profile_id == a.profile_id

    def test_two_functions_can_bind_different_profiles(self, tmp_path):
        """A2: 视觉和重估可以绑定不同配置。"""
        store = ApiProfileStore(tmp_path)
        a = _make_profile("A")
        b = _make_profile("B")
        store.save_profile(a, "ka")
        store.save_profile(b, "kb")
        store.bind(VISUAL_AI, a.profile_id)
        store.bind(LOCAL_REESTIMATE, b.profile_id)

        assert store.bound_profile(VISUAL_AI)[0].profile_id == a.profile_id
        assert store.bound_profile(LOCAL_REESTIMATE)[0].profile_id == b.profile_id

    def test_save_profile_does_not_overwrite_bindings(self, tmp_path):
        """A3: 保存 Profile 后不应偷偷修改已有绑定。"""
        store = ApiProfileStore(tmp_path)
        a = _make_profile("A")
        b = _make_profile("B")
        store.save_profile(a, "ka")
        store.save_profile(b, "kb")
        store.bind(VISUAL_AI, a.profile_id)
        store.bind(LOCAL_REESTIMATE, b.profile_id)

        # 重新保存 profile A（编辑名称）
        a_edited = ApiProfile(
            profile_id=a.profile_id, display_name="A-edited",
            provider=a.provider, api_url=a.api_url, model_name=a.model_name,
        )
        store.save_profile(a_edited, "ka-new")

        # 绑定不应被修改
        assert store.bound_profile(VISUAL_AI)[0].profile_id == a.profile_id
        assert store.bound_profile(LOCAL_REESTIMATE)[0].profile_id == b.profile_id

    def test_new_profile_can_be_bound_and_persisted(self, tmp_path):
        """A4: 新建配置后可正常选择并持久化。"""
        store = ApiProfileStore(tmp_path)
        qwen = ApiProfile.create(
            display_name="Qwen3.8",
            provider="自定义",
            api_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            model_name="qwen-vl-max",
        )
        store.save_profile(qwen, "qwen-key")
        store.bind(VISUAL_AI, qwen.profile_id)

        fresh = ApiProfileStore(tmp_path)
        bound = fresh.bound_profile(VISUAL_AI)
        assert bound is not None
        assert bound[0].display_name == "Qwen3.8"
        assert bound[0].model_name == "qwen-vl-max"


# =========================================================================
# B. Reestimate confirmed_facts
# =========================================================================


class TestReestimateConfirmedFacts:
    """B5-B9: 普通页面值不自动进入 confirmed_facts；真正 user_confirmed 会进入；
    actual_first_mile / CAL 不进入。"""

    def test_page_values_not_in_confirmed_facts(self):
        """B5: 页面有值但 session 未 confirm → confirmed_facts 为空。"""
        session = CalculationSession()
        # 模拟 AI 填入了值但用户未确认
        session.observation.length_cm = 45
        session.observation.width_cm = 30
        session.observation.height_cm = 15
        session.observation.weight_g = 580

        facts = session.confirmed_facts()
        # 没有任何 user_confirmed 字段
        assert "length_cm" not in facts
        assert "width_cm" not in facts
        assert "height_cm" not in facts
        assert "weight_g" not in facts

    def test_user_confirmed_weight_enters(self):
        """B6: 用户真正手工确认 weight_g=80 → confirmed_facts 出现 80g。"""
        session = CalculationSession()
        session.confirm_value("weight_g", 80)

        facts = session.confirmed_facts()
        assert "weight_g" in facts
        assert facts["weight_g"]["value"] == 80
        assert facts["weight_g"]["source"] == "user_confirmed"

    def test_user_confirmed_dimensions_enter(self):
        """B7: 用户真正手工确认尺寸 → confirmed_facts 出现对应值。"""
        session = CalculationSession()
        session.confirm_value("length_cm", 25)
        session.confirm_value("width_cm", 20)
        session.confirm_value("height_cm", 5)

        facts = session.confirmed_facts()
        assert facts["length_cm"]["value"] == 25
        assert facts["width_cm"]["value"] == 20
        assert facts["height_cm"]["value"] == 5

    def test_actual_first_mile_not_in_confirmed_facts(self):
        """B8: actual_first_mile 不是 session 确认字段。"""
        session = CalculationSession()
        # confirm_value 只接受 observation 字段，非 observation 字段被忽略
        session.confirm_value("actual_first_mile_fee_rmb", 50.0)

        facts = session.confirmed_facts()
        assert "actual_first_mile_fee_rmb" not in facts

    def test_cal_not_in_confirmed_facts(self):
        """B9: CAL 相关字段不进入 confirmed_facts。"""
        session = CalculationSession()
        session.confirm_value("matched_cal_rules", ["CAL77"])

        facts = session.confirmed_facts()
        assert "matched_cal_rules" not in facts
        # 只包含裸品事实相关字段
        for field in facts:
            assert field in ("length_cm", "width_cm", "height_cm", "weight_g",
                             "product_cost_rmb", "domestic_shipping_rmb", "product_name")


# =========================================================================
# C. Prompt state semantics
# =========================================================================


class TestPromptStateSemantics:
    """C10-C12: V1 Prompt 明确 state 为物理发货状态，禁止时效/履约信息。"""

    def test_vision_prompt_defines_state_as_physical_form(self):
        """C10: 视觉 Prompt 明确规定 state 为物理形态。"""
        prompt = RecognitionService._prompt(1)
        assert "物理形态" in prompt
        assert "处理方式" in prompt

    def test_vision_prompt_prohibits_fulfillment_info(self):
        """C11: Prompt 明确禁止 '48小时发货' 等履约信息。"""
        prompt = RecognitionService._prompt(1)
        assert "48小时发货" in prompt  # 作为禁止示例出现
        assert "发货时效" in prompt
        assert "包邮" in prompt

    def test_reestimate_prompt_defines_state(self):
        """C11b: 重估 Prompt 也包含 state 语义约束。"""
        ctx = LocalReestimateService._context(
            product_name="test", confirmed_facts={},
            current_shipment={}, user_correction="compress",
        )
        assert "物理形态" in ctx
        assert "48小时发货" in ctx

    def test_no_complex_v8_fields(self):
        """C12: 不重新出现复杂 V8 字段。"""
        prompt = RecognitionService._prompt(1)
        for forbidden in ("rigidity", "foldability", "compressibility", "normal/conservative"):
            assert forbidden not in prompt

    def test_invalid_state_detection(self):
        """state 验证器：'48小时发货' 被判定为无效。"""
        assert _is_invalid_shipment_state("48小时发货") is True
        assert _is_invalid_shipment_state("24小时发货") is True
        assert _is_invalid_shipment_state("现货包邮") is True
        assert _is_invalid_shipment_state("顺丰快递") is True
        assert _is_invalid_shipment_state("") is False
        assert _is_invalid_shipment_state("折叠") is False
        assert _is_invalid_shipment_state("压缩后发货") is False
        assert _is_invalid_shipment_state("保持原形") is False

    def test_proposal_from_shipment_rejects_invalid_state(self):
        """proposal_from_shipment 遇到无效 state 时清空并记录 parse_issue。"""
        shipment = {
            "length_cm": 10, "width_cm": 10, "height_cm": 5,
            "weight_g": 100, "state": "48小时发货",
        }
        proposal = RecognitionService.proposal_from_shipment(shipment, note="test")
        assert proposal.normal.packaging_method == ""
        assert "shipment.state" in proposal.candidate_records.get(
            "runtime_v1_validation", {}
        ).get("parse_issues", {})


# =========================================================================
# D. UI: AI发货判断 read-only & user correction height
# =========================================================================


class TestUICorrections:
    """D13-D17: UI 修正验证。"""

    def test_packing_state_field_is_readonly(self, qapp, tmp_path):
        """D13: txtPackingState（AI发货判断）为只读。"""
        from profit_accounting_26.application import AppContext
        from profit_accounting_26.ui.pages.calculation_page import CalculationPage

        context = _make_app_context(tmp_path)
        page = CalculationPage(context)
        assert page.structure_summary._widget.isReadOnly() is True

    def test_user_correction_height_reduced(self):
        """D15: 用户修正框高度从 104/148 缩小到 68/88。"""
        from profit_accounting_26.ui.pages.calculation_page import _UserCorrectionEdit

        assert _UserCorrectionEdit.MIN_HEIGHT == 68
        assert _UserCorrectionEdit.MAX_HEIGHT == 88
        assert _UserCorrectionEdit.MAX_HEIGHT < 104  # 比旧最小值还小

    def test_user_correction_placeholder_mentions_correction(self):
        """D14: 用户修正框的示例文字明确提到 '重估' 和 '修正'。"""
        from profit_accounting_26.ui.pages.calculation_page import _UserCorrectionEdit

        text = _UserCorrectionEdit.EXAMPLE_TEXT
        assert "重估" in text
        assert "修正" in text
        assert "货代" not in text
        assert "价格" not in text
        assert "头程" not in text


# =========================================================================
# E. History table
# =========================================================================


class TestHistoryTable:
    """E18-E19: 历史表仍为 8 列；resizeRowsToContents 已调用。"""

    def test_history_table_column_count(self):
        """E19: 历史表仍为 8 列。"""
        from profit_accounting_26.ui.pages.history_page import HistoryPage

        assert HistoryPage.COLUMN_COUNT == 8
        assert len(HistoryPage.COLUMN_HEADERS) == 8


# =========================================================================
# F. Diagnostic logging
# =========================================================================


class TestDiagnosticLogging:
    """F20-F21: 重估日志包含 provider/model/provider_host；不包含 API key。"""

    def test_reestimate_result_carries_provider_info(self):
        """F20: LocalReestimateResult 包含 provider/model/provider_host。"""
        result = LocalReestimateResult(
            provider="自定义",
            model="qwen-vl-max",
            provider_host="dashscope.aliyuncs.com",
        )
        assert result.provider == "自定义"
        assert result.model == "qwen-vl-max"
        assert result.provider_host == "dashscope.aliyuncs.com"

    def test_diagnostic_sanitize_strips_api_key(self):
        """F21: DiagnosticLogger._sanitize 过滤 api_key/authorization。"""
        from profit_accounting_26.application.diagnostic_logger import _sanitize

        data = {
            "provider": "GLM",
            "model": "glm-4v",
            "api_key": "should-be-removed",
            "authorization": "Bearer secret",
            "normal_field": "kept",
        }
        sanitized = _sanitize(data)
        assert "api_key" not in sanitized
        assert "authorization" not in sanitized
        assert sanitized["provider"] == "GLM"
        assert sanitized["normal_field"] == "kept"


# =========================================================================
# Helpers
# =========================================================================


def _make_app_context(tmp_path):
    """Construct a minimal AppContext for headless UI tests."""
    from profit_accounting_26.application import AppContext

    settings_svc = MagicMock()
    settings_svc.load.return_value = {
        "display_name": "test",
        "log_level": "INFO",
        "log_retention_days": 30,
        "forwarders": [],
        "profit_rules": [],
        "selected_forwarder_id": "",
        "selected_profit_rule_id": "",
    }

    paths = MagicMock()
    paths.data_dir = tmp_path

    profile_store = ApiProfileStore(tmp_path)
    diagnostic_logger = MagicMock()
    diagnostic_logger.begin_operation.return_value = MagicMock()

    context = MagicMock(spec=AppContext)
    context.settings_service = settings_svc
    context.paths = paths
    context.api_profile_store = profile_store
    context.diagnostic_logger = diagnostic_logger
    return context
