"""PR #14 最终合同回归：事实替换、Prompt、Provider、设置与利润状态机。"""

from __future__ import annotations

from dataclasses import asdict
import json

import pytest
from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QLineEdit, QTextEdit, QWidget

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.api_profile_store import (
    ApiProfile,
    ApiProfileStore,
    LOCAL_REESTIMATE,
    PROVIDER_PRESETS,
    VISUAL_AI,
)
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.application.settings_service import DEFAULT_SUBSIDY_RULE, SettingsService
from profit_accounting_26.domain.models import AIObservation
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.ui.binders.calculation_binder import (
    CalculationBinder,
    DRIVER_ACTIVITY_PROFIT,
    DRIVER_PROFIT_RATE,
)
from profit_accounting_26.ui.pages.calculation_page import CalculationPage
from profit_accounting_26.ui.pages.settings_page import SettingsPage
from profit_accounting_26.ui.ui_loader import load_main_window


class _Settings:
    def load(self):
        return {"exchange_rate_usd_to_rmb": 7.2}


class _Context:
    settings_service = _Settings()


@pytest.fixture
def binder(qapp):
    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    result = CalculationBinder(page, _Context())
    result._ui_root_ref = ui
    yield result


@pytest.fixture
def app_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ApplicationPaths, "configured_data_dir", classmethod(lambda cls: None))
    return AppContext.create_default()


def test_new_visual_null_clears_unconfirmed_bare_facts_and_keeps_shipment(qapp, app_context):
    page = CalculationPage(app_context)
    try:
        page.product_cost.setValue(18.8)
        page.domestic_shipping.setValue(5.0)
        page.bare_length.setValue(45)
        page.bare_width.setValue(30)
        page.bare_height.setValue(15)
        page.bare_weight.setValue(580)
        assert page.session.confirmed_facts() == {}

        observation = AIObservation()
        page._apply_observation(observation)
        proposal = RecognitionService.proposal_from_shipment(
            {
                "length_cm": 20,
                "width_cm": 15,
                "height_cm": 3,
                "weight_g": 60,
                "state": "可折叠；袋装发货",
            }
        )
        page.apply_proposal(proposal)

        assert page.product_cost.value() == 0
        assert page.domestic_shipping.value() == 0
        assert page.bare_length.value() == 0
        assert page.bare_width.value() == 0
        assert page.bare_height.value() == 0
        assert page.bare_weight.value() == 0
        assert page.normal_fields["length"].value() == 20
        assert page.normal_fields["width"].value() == 15
        assert page.normal_fields["height"].value() == 3
        assert page.normal_fields["weight"].value() == 60
        assert page.normal_fields["method"].text() == "可折叠；袋装发货"
    finally:
        page.deleteLater()


def test_user_confirmed_weight_survives_new_visual_null(qapp, app_context):
    page = CalculationPage(app_context)
    try:
        page.bare_weight.setValue(80)
        page.session.confirm_value("weight_g", 80)
        observation = AIObservation()
        page.session.protect_confirmed_values(observation)
        page._apply_observation(observation)
        assert page.bare_weight.value() == 80
        assert observation.weight_g == 80
        assert page.session.confirmed_facts()["weight_g"]["value"] == 80
    finally:
        page.deleteLater()


def test_ai_shipment_judgment_has_one_visible_contract_location(qapp, app_context):
    page = CalculationPage(app_context)
    try:
        top_title = page._root.findChild(QLabel, "lblPackingStateTitle")
        top_field = page._root.findChild(QLineEdit, "txtPackingState")
        card_title = page._root.findChild(QLabel, "lblAiShipmentJudgment")
        card_field = page.normal_fields["method"]._widget
        assert top_title is not None and top_title.isHidden()
        assert top_field is not None and top_field.isHidden()
        assert card_title is not None and card_title.text() == "AI发货判断"
        assert isinstance(card_field, QTextEdit) and card_field.isReadOnly()
    finally:
        page.deleteLater()


def test_visual_and_reestimate_prompts_are_frozen_minimal_contracts():
    assert RecognitionService.PROMPT_VERSION == "2.6.1-visual-v1.2-frozen"
    assert LocalReestimateService.PROMPT_VERSION == "2.6.1-reestimate-v1.1-frozen"
    schema = RecognitionService.RESPONSE_SCHEMA
    assert set(schema["properties"]) == {"product_name", "observed", "bare_estimate", "shipment", "note"}
    assert "bare_estimate" in schema["properties"]
    be_schema = schema["properties"]["bare_estimate"]
    assert set(be_schema["required"]) == {"length_cm", "width_cm", "height_cm", "weight_g"}
    prompt = RecognitionService._prompt(2)
    assert "bare_estimate" in prompt
    reestimate = LocalReestimateService._context(
        product_name="商品", confirmed_facts={}, current_shipment={}, user_correction="修正",
    )
    for text in (prompt, reestimate):
        assert "主要物理形态/处理状态" in text
        assert "简单包装方式" in text
        assert "可折叠；袋装发货" in text
        assert "不要只返回" in text
    serialized_schema = json.dumps(schema, ensure_ascii=False)
    for forbidden in (
        "rigidity", "foldability", "compressibility", "normal", "conservative",
        "package_type", "container_type", "packing_action",
    ):
        assert forbidden not in serialized_schema


@pytest.mark.parametrize(
    ("provider", "expected"),
    (
        ("阿里云百炼", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
        ("DeepSeek", "https://api.deepseek.com/chat/completions"),
        ("GLM", "https://open.bigmodel.cn/api/paas/v4/chat/completions"),
        ("OpenAI", "https://api.openai.com/v1/chat/completions"),
    ),
)
def test_offline_provider_preset_endpoint_contract(provider, expected):
    preset = PROVIDER_PRESETS[provider]
    assert RecognitionService._endpoint(preset) == expected
    assert LocalReestimateService._endpoint(preset) == expected


def test_api_binding_save_does_not_overwrite_forwarders_or_profit_rules(
    qapp, app_context, monkeypatch,
):
    forwarder = asdict(SettingsService.new_forwarder("测试货代", 100.0, 5.0, 6000.0))
    settings = app_context.settings_service.load()
    settings.update(
        {
            "forwarders": [forwarder],
            "selected_forwarder_id": forwarder["id"],
            "profit_rules": [dict(DEFAULT_SUBSIDY_RULE)],
            "selected_profit_rule_id": DEFAULT_SUBSIDY_RULE["id"],
        }
    )
    app_context.settings_service.save(settings)

    page = SettingsPage(app_context)
    try:
        # 模拟 API 保存时页面上的其他分组尚未同步；这些空 UI 状态不得
        # 覆盖 settings.json 中已经持久化的业务设置。
        page.forwarder_table.setRowCount(0)
        page.rules_data = []
        profile = ApiProfile.create(
            display_name="Qwen",
            provider="阿里云百炼",
            api_url=PROVIDER_PRESETS["阿里云百炼"],
            model_name="qwen3.8-max",
        )
        app_context.api_profile_store.save_profile(profile, "test-key")
        page._refresh_api_profiles()
        page.visual_binding.setCurrentIndex(page.visual_binding.findData(profile.profile_id))
        page.local_binding.setCurrentIndex(page.local_binding.findData(profile.profile_id))
        monkeypatch.setattr(
            "profit_accounting_26.ui.pages.settings_page.QMessageBox.information",
            lambda *args, **kwargs: None,
        )
        page.save_settings()
    finally:
        page.deleteLater()

    fresh_settings = SettingsService(app_context.paths.settings_path).load()
    fresh_store = ApiProfileStore(app_context.paths.data_dir)
    assert fresh_settings["forwarders"] == [forwarder]
    assert fresh_settings["selected_forwarder_id"] == forwarder["id"]
    assert fresh_settings["profit_rules"] == [dict(DEFAULT_SUBSIDY_RULE)]
    assert fresh_settings["selected_profit_rule_id"] == DEFAULT_SUBSIDY_RULE["id"]
    assert fresh_store.bound_profile(VISUAL_AI)[0].profile_id == profile.profile_id
    assert fresh_store.bound_profile(LOCAL_REESTIMATE)[0].profile_id == profile.profile_id


def test_new_record_defaults_and_reset_are_15_and_25(binder):
    assert binder.spin_reserve.value() == pytest.approx(15.0)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)
    binder.spin_reserve.setValue(18.0)
    binder.spin_profit_rate.setValue(32.0)
    binder.reset()
    assert binder.spin_reserve.value() == pytest.approx(15.0)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)
    assert binder._profit_driver == DRIVER_PROFIT_RATE


def test_cost_reserve_and_rate_changes_keep_sticky_inputs(binder):
    binder.set_calculation_cost(100.0)
    initial_price = binder.txt_na_price_usd.value()
    binder.set_calculation_cost(160.0)
    assert binder.spin_reserve.value() == pytest.approx(15.0)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)
    assert binder.txt_na_price_usd.value() != pytest.approx(initial_price)

    binder.spin_reserve.setValue(20.0)
    assert binder.spin_reserve.value() == pytest.approx(20.0)
    assert binder.spin_profit_rate.value() == pytest.approx(25.0)

    price_at_25 = binder.txt_na_price_usd.value()
    binder.spin_profit_rate.setValue(30.0)
    assert binder.spin_reserve.value() == pytest.approx(20.0)
    assert binder.spin_profit_rate.value() == pytest.approx(30.0)
    assert binder.txt_na_price_usd.value() != pytest.approx(price_at_25)


def test_explicit_activity_profit_driver_is_preserved_but_reserve_is_not_changed(binder):
    binder.set_calculation_cost(100.0)
    binder.spin_reserve.setValue(18.0)
    binder.txt_act_profit_rmb.setValue(40.0)
    assert binder._profit_driver == DRIVER_ACTIVITY_PROFIT
    assert binder.spin_reserve.value() == pytest.approx(18.0)
    assert binder.spin_profit_rate.value() == pytest.approx(40.0)


def test_profit_snapshot_restores_last_reserve_and_rate(binder, qapp):
    binder.set_calculation_cost(120.0)
    binder.spin_reserve.setValue(18.0)
    binder.spin_profit_rate.setValue(32.0)
    snapshot = binder.export_profit_scenarios()

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    restored = CalculationBinder(page, _Context())
    restored._ui_root_ref = ui
    restored.load_from_record({"profit_scenarios": snapshot})
    assert restored.spin_reserve.value() == pytest.approx(18.0)
    assert restored.spin_profit_rate.value() == pytest.approx(32.0)
    assert restored.is_in_snapshot_mode()


def test_profit_ui_object_names_and_three_groups_exist(qapp, app_context):
    page = CalculationPage(app_context)
    try:
        for name in (
            "spinPromotionReserve", "spinProfitRate", "txtCalculatedCostRmb",
            "txtNoActivityPriceRmb", "txtNoActivityPriceUsd",
            "txtActivityProfitRmb", "txtActivityProfitUsd",
            "txtSheinPriceRmb", "txtSheinPriceUsd",
            "txtCalculatedCostUsd", "txtNoActivityProfitRmb",
            "txtActivityPriceRmb", "txtActivityPriceUsd",
        ):
            assert page._root.findChild(QWidget, name) is not None, f"missing widget: {name}"
        # 不再存在竖向分隔线
        assert page._root.findChild(QWidget, "profitSeparator_col2") is None
        assert page._root.findChild(QWidget, "profitSeparator_col7") is None
        # 裸尺寸/裸重来源标签存在
        assert page._root.findChild(QWidget, "lblBareDimensionSource") is not None
        assert page._root.findChild(QWidget, "lblBareWeightSource") is not None
    finally:
        page.deleteLater()


def test_save_current_rule_persists_to_settings_service(qapp, app_context):
    """save_current_rule 必须立即将规则写入 SettingsService，而非仅内存。"""
    page = SettingsPage(app_context)
    try:
        page.rule_list.setCurrentRow(0)
        original_count = len(page.rules_data)
        # 新增规则
        page.add_rule()
        new_rule_row = page.rule_list.count() - 1
        page.rule_list.setCurrentRow(new_rule_row)
        # 修改规则名称
        page.rule_name.setText("测试持久化规则")
        page.rule_condition_value.setValue(10.0)
        page.rule_value.setValue(5.0)
        # 保存规则 —— 必须立即持久化
        page.save_current_rule()
        # 验证：从 SettingsService 重新加载，规则存在
        fresh_settings = SettingsService(app_context.paths.settings_path).load()
        rule_names = [r.get("name") for r in fresh_settings.get("profit_rules", [])]
        assert "测试持久化规则" in rule_names
        # 验证：规则总数正确（原有 + 新增）
        assert len(fresh_settings.get("profit_rules", [])) == original_count + 1
    finally:
        page.deleteLater()


def test_saved_rule_survives_settings_page_recreation(qapp, app_context):
    """保存规则后重新创建 SettingsPage，规则仍存在。"""
    page = SettingsPage(app_context)
    try:
        page.add_rule()
        page.rule_list.setCurrentRow(page.rule_list.count() - 1)
        page.rule_name.setText("跨页面存活规则")
        page.rule_condition_value.setValue(20.0)
        page.rule_value.setValue(3.0)
        page.save_current_rule()
    finally:
        page.deleteLater()
    # 重新创建 SettingsPage
    page2 = SettingsPage(app_context)
    try:
        rule_names = [r.get("name") for r in page2.rules_data]
        assert "跨页面存活规则" in rule_names
    finally:
        page2.deleteLater()


def test_archive_current_rule_persists_immediately(qapp, app_context, monkeypatch):
    """archive_current_rule 必须立即持久化归档状态。"""
    # 模拟确认弹窗：必须在 settings_page 模块中 monkeypatch
    monkeypatch.setattr(
        "profit_accounting_26.ui.pages.settings_page.confirm_action",
        lambda *a, **k: True,
    )
    page = SettingsPage(app_context)
    try:
        # 确保至少有一条规则
        if not page.rules_data:
            page.add_rule()
            page.rule_list.setCurrentRow(page.rule_list.count() - 1)
            page.rule_name.setText("待归档规则")
            page.save_current_rule()
        page.rule_list.setCurrentRow(0)
        rule_id = page.rules_data[page.visible_rule_indices[0]].get("id")
        page.archive_current_rule()
        # 验证：从 SettingsService 重新加载，规则已归档
        fresh_settings = SettingsService(app_context.paths.settings_path).load()
        archived_rules = [
            r for r in fresh_settings.get("profit_rules", [])
            if r.get("id") == rule_id and r.get("archived")
        ]
        assert len(archived_rules) == 1
    finally:
        page.deleteLater()


# ---------------------------------------------------------------------------
# bare_estimate 层级测试
# ---------------------------------------------------------------------------

def test_bare_estimate_fallback_when_observed_null(qapp, app_context):
    """observed=null + bare_estimate=45g：页面显示 45g，source=AI估算。"""
    page = CalculationPage(app_context)
    try:
        obs = AIObservation()
        obs.raw_payload = {
            "bare_estimate": {"length_cm": 10.0, "width_cm": 8.0, "height_cm": 3.0, "weight_g": 45.0},
            "observation": {},
        }
        page._apply_observation(obs)
        assert page.bare_weight.value() == 45.0
        assert page.bare_length.value() == 10.0
        assert page.lbl_bare_weight_source.text() == "AI\u4f30\u7b97"
        assert page.lbl_bare_dim_source.text() == "AI\u4f30\u7b97"
    finally:
        page.deleteLater()


def test_observed_takes_priority_over_bare_estimate(qapp, app_context):
    """observed=50g + bare_estimate=45g：页面显示 50g，source=图片识别。"""
    page = CalculationPage(app_context)
    try:
        obs = AIObservation(weight_g=50.0, length_cm=12.0, width_cm=10.0, height_cm=4.0)
        obs.dimension_value_source = "image_text"
        obs.weight_value_source = "image_text"
        obs.raw_payload = {
            "bare_estimate": {"length_cm": 10.0, "width_cm": 8.0, "height_cm": 3.0, "weight_g": 45.0},
            "observation": {},
        }
        page._apply_observation(obs)
        assert page.bare_weight.value() == 50.0
        assert page.bare_length.value() == 12.0
        assert page.lbl_bare_weight_source.text() == "\u56fe\u7247\u8bc6\u522b"
        assert page.lbl_bare_dim_source.text() == "\u56fe\u7247\u8bc6\u522b"
    finally:
        page.deleteLater()


def test_user_confirmed_not_overwritten_by_bare_estimate(qapp, app_context):
    """user_confirmed=52g：页面保持 52g，source=用户确认。"""
    page = CalculationPage(app_context)
    try:
        page.bare_weight.setValue(52.0)
        page.session.confirm_value("weight_g", 52.0)
        obs = AIObservation()
        obs.raw_payload = {
            "bare_estimate": {"length_cm": 10.0, "width_cm": 8.0, "height_cm": 3.0, "weight_g": 45.0},
            "observation": {},
        }
        page.session.protect_confirmed_values(obs)
        page._apply_observation(obs)
        assert page.bare_weight.value() == 52.0
        assert page.lbl_bare_weight_source.text() == "\u7528\u6237\u786e\u8ba4"
    finally:
        page.deleteLater()


def test_bare_estimate_not_in_confirmed_facts(qapp, app_context):
    """bare_estimate 不得进入 confirmed_facts。"""
    page = CalculationPage(app_context)
    try:
        obs = AIObservation()
        obs.raw_payload = {
            "bare_estimate": {"length_cm": 10.0, "width_cm": 8.0, "height_cm": 3.0, "weight_g": 45.0},
            "observation": {},
        }
        page._apply_observation(obs)
        facts = page.session.confirmed_facts()
        # bare_estimate 自动填充不应产生 user_confirmed 记录
        assert "weight_g" not in facts
        assert "length_cm" not in facts
    finally:
        page.deleteLater()


def test_shipment_does_not_backfill_observed(qapp, app_context):
    """shipment 不得反填 observed。"""
    page = CalculationPage(app_context)
    try:
        obs = AIObservation()
        obs.raw_payload = {
            "bare_estimate": {},
            "observation": {},
        }
        page._apply_observation(obs)
        proposal = RecognitionService.proposal_from_shipment(
            {"length_cm": 20, "width_cm": 15, "height_cm": 3, "weight_g": 60, "state": "\u53ef\u6298\u53e0\uff1b\u888b\u88c5\u53d1\u8d27"}
        )
        page.apply_proposal(proposal)
        # shipment 值在包装卡片中，不应反填裸尺寸/裸重
        assert page.bare_length.value() == 0
        assert page.bare_weight.value() == 0
    finally:
        page.deleteLater()


def test_reestimate_schema_unchanged():
    """Reestimate Prompt/Schema 不因本轮扩张。"""
    schema = LocalReestimateService.RESPONSE_SCHEMA
    assert set(schema["properties"]) == {"shipment", "note"}
    assert "bare_estimate" not in schema["properties"]
    assert LocalReestimateService.PROMPT_VERSION == "2.6.1-reestimate-v1.1-frozen"


def test_old_record_without_bare_estimate_loads(qapp, app_context):
    """旧记录无 bare_estimate 时正常读取。"""
    page = CalculationPage(app_context)
    try:
        obs = AIObservation()
        obs.raw_payload = {"observation": {}}  # 没有 bare_estimate
        page._apply_observation(obs)
        assert page.bare_weight.value() == 0
        assert page.bare_length.value() == 0
        assert page.lbl_bare_weight_source.text() == "\u672a\u8bc6\u522b"
        assert page.lbl_bare_dim_source.text() == "\u672a\u8bc6\u522b"
    finally:
        page.deleteLater()
