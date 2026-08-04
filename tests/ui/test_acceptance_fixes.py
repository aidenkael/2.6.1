"""验收修正轮回归测试（真实 Binder / CalculationPage / MainWindow 路径）。

覆盖四个阻塞问题的修正：
1. 活动预留联动：4 种 driver 下修改 spinPromotionReserve 均保持无活动售价 USD 不变；
2. 记录打开与快照：保存时汇率/规则ID集合/完整规则快照/旧记录标记；
   新记录重开与保存时一致且不静默按当前设置重算；旧记录只恢复无活动历史；
   真实 CalculationPage 保存—修改设置—重开往返；
3. 多规则实际计算：cmbProfitRule 运行时“全部启用规则”，多规则合计、净合计标签、tooltip；
4. 版本标题：删除“2.6”强制设置，标题来自 main_window.ui（运行时 2.6.1）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtWidgets import QApplication

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.ui.binders.calculation_binder import (
    ALL_ENABLED_RULES_ID,
    DRIVER_ACTIVITY_PROFIT,
    DRIVER_NO_ACTIVITY_PRICE,
    DRIVER_NO_ACTIVITY_PROFIT,
    DRIVER_PROFIT_RATE,
)

RATE = 7.2


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class MockSettingsService:
    def load(self):
        return {"exchange_rate_usd_to_rmb": RATE}


class MockContext:
    settings_service = MockSettingsService()


def _income_rule(rule_id, name, threshold, amount_usd):
    return AdjustmentRule(
        id=rule_id,
        name=name,
        condition_field="sale_price_usd",
        compare_op=CompareOp.LT,
        condition_value=threshold,
        direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED,
        adjustment_value=amount_usd,
        currency="USD",
    )


@pytest.fixture
def binder(qapp):
    from PySide6.QtWidgets import QWidget

    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
    from profit_accounting_26.ui.ui_loader import load_main_window

    ui = load_main_window()
    page = ui.findChild(QWidget, "pageCalculation")
    b = CalculationBinder(page, MockContext())
    b._ui_root_ref = ui  # 防止 .ui 根节点被 GC，导致子控件 C++ 对象销毁
    yield b


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


# ---------------------------------------------------------------------------
# 修正 1：活动预留联动（4 种 driver 均保持无活动售价不变）
# ---------------------------------------------------------------------------


def test_reserve_keeps_na_price_driver_no_activity_price(binder):
    binder.set_calculation_cost(100.0)
    binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
    binder.txt_na_price_usd.setValue(30.0)
    assert binder.txt_na_price_usd.value() == pytest.approx(30.0)

    binder.spin_reserve.setValue(20.0)

    assert binder.txt_na_price_usd.value() == pytest.approx(30.0)
    assert binder._no_activity_price_usd == pytest.approx(30.0)
    assert binder.txt_act_price_usd.value() == pytest.approx(24.0)
    # 活动预留变化后利润率被重算
    expected_rate = (24.0 * RATE - 100.0) / 100.0 * 100.0
    assert binder.spin_profit_rate.value() == pytest.approx(expected_rate, abs=0.02)


def _setup_profit_rate_driver(binder):
    binder.set_calculation_cost(100.0)
    binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
    binder.txt_na_price_usd.setValue(40.0)
    binder._profit_driver = DRIVER_PROFIT_RATE
    return binder.spin_profit_rate.value()


@pytest.mark.parametrize(
    "driver_setup",
    [DRIVER_PROFIT_RATE, DRIVER_NO_ACTIVITY_PROFIT, DRIVER_ACTIVITY_PROFIT],
)
def test_reserve_keeps_na_price_other_drivers(binder, driver_setup):
    """profit_rate / no_activity_profit / activity_profit 三种 driver 下，
    修改活动预留不得反推改写无活动售价。"""
    binder.set_calculation_cost(100.0)
    # 先在 no_activity_price driver 下建立 30 USD 基准
    binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
    binder.txt_na_price_usd.setValue(30.0)
    na_before = binder._no_activity_price_usd
    assert na_before == pytest.approx(30.0)

    if driver_setup == DRIVER_PROFIT_RATE:
        binder._profit_driver = DRIVER_PROFIT_RATE
        # 记录当前利润率，之后改预留不应为保持利润率而改售价
        binder.spin_profit_rate.value()
    elif driver_setup == DRIVER_NO_ACTIVITY_PROFIT:
        binder._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
    else:
        binder._profit_driver = DRIVER_ACTIVITY_PROFIT
        binder.txt_act_profit_rmb.setValue(binder.txt_act_profit_rmb.value())

    binder.spin_reserve.setValue(25.0)

    # 无活动售价完全不变
    assert binder._no_activity_price_usd == pytest.approx(30.0)
    assert binder.txt_na_price_usd.value() == pytest.approx(30.0)
    # 活动后售价按新预留重算：30 × 0.75 = 22.5
    assert binder.txt_act_price_usd.value() == pytest.approx(22.5)


# ---------------------------------------------------------------------------
# 修正 3：多规则实际计算（cmbProfitRule “全部启用规则”，真实 Binder 计算路径）
# ---------------------------------------------------------------------------


class TestMultiRuleRealBinderPath:
    def test_combo_contains_all_enabled_option(self, binder):
        rules = (_income_rule("r1", "补贴A", 29.0, 2.99), _income_rule("r2", "补贴B", 29.0, 1.00))
        binder.set_rules(rules)
        assert binder.cmb_role_find(ALL_ENABLED_RULES_ID) >= 0
        assert binder.cmb_rule.itemText(binder.cmb_role_find(ALL_ENABLED_RULES_ID)) == "全部启用规则"

    def test_all_enabled_rules_participate_via_refresh(self, binder):
        rules = (_income_rule("r1", "补贴A", 29.0, 2.99), _income_rule("r2", "补贴B", 29.0, 1.00))
        binder.set_rules(rules)
        binder.set_calculation_cost(100.0)
        binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        binder.txt_na_price_usd.setValue(20.0)
        idx = binder.cmb_role_find(ALL_ENABLED_RULES_ID)
        assert idx >= 0
        binder.cmb_rule.setCurrentIndex(idx)
        binder._refresh_all()

        active = binder._active_rules()
        assert {r.id for r in active} == {"r1", "r2"}
        # 收入分别合计：(2.99 + 1.00) × 7.2 = 28.728，净合计显示
        expected_net = (2.99 + 1.00) * RATE
        assert binder.lbl_na_status.text() == f"已触发 +¥{expected_net:.2f}"
        # tooltip 列出全部命中规则
        tip = binder.lbl_na_status.toolTip()
        assert "补贴A" in tip and "补贴B" in tip

    def test_two_scenarios_judge_independently_all_rules(self, binder):
        rules = (_income_rule("r1", "补贴A", 29.0, 2.99), _income_rule("r2", "补贴B", 29.0, 1.00))
        binder.set_rules(rules)
        binder.set_calculation_cost(100.0)
        binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        binder.txt_na_price_usd.setValue(30.0)
        binder.spin_reserve.setValue(10.0)
        binder.cmb_rule.setCurrentIndex(binder.cmb_role_find(ALL_ENABLED_RULES_ID))
        binder._refresh_all()

        # 无活动 30 >= 29 → 两条都未触发；活动 27 < 29 → 两条都触发
        assert binder.lbl_na_status.text() == "未触发"
        expected_net = (2.99 + 1.00) * RATE
        assert binder.lbl_act_status.text() == f"已触发 +¥{expected_net:.2f}"
        assert "补贴A" in binder.lbl_act_status.toolTip()
        assert "补贴B" in binder.lbl_act_status.toolTip()


# ---------------------------------------------------------------------------
# 修正 2：记录打开与快照（真实 CalculationPage 保存—改设置—重开）
# ---------------------------------------------------------------------------


def _fill_and_save(page, monkeypatch, rule_id=ALL_ENABLED_RULES_ID, na_price=30.0):
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    page.product_cost.setValue(35.0)
    page.domestic_shipping.setValue(5.0)
    page.normal_fields["length"].setValue(25.0)
    page.normal_fields["width"].setValue(18.0)
    page.normal_fields["height"].setValue(6.0)
    page.normal_fields["weight"].setValue(320.0)
    page.recalculate()
    assert page.current_quote is not None
    b = page.profit_binder
    b._profit_driver = DRIVER_NO_ACTIVITY_PRICE
    b.txt_na_price_usd.setValue(na_price)
    b.spin_reserve.setValue(10.0)
    idx = b.cmb_role_find(rule_id)
    assert idx >= 0
    b.cmb_rule.setCurrentIndex(idx)
    b._refresh_all()
    page.save_record()
    assert page.record_id
    return b


def test_real_page_save_modify_settings_reopen_keeps_snapshot(qapp, temp_context, monkeypatch):
    from profit_accounting_26.ui.pages import CalculationPage

    page = CalculationPage(temp_context)
    try:
        b = _fill_and_save(page, monkeypatch)
        saved_na_profit = b.txt_na_profit_rmb.value()
        saved_act_profit = b.txt_act_profit_rmb.value()
        saved_act_price = b.txt_act_price_usd.value()
        saved_rate = b.spin_profit_rate.value()
        record_id = page.record_id
        snapshot = b.export_profit_scenarios()
        assert snapshot["exchange_rate"] == pytest.approx(RATE)
        assert snapshot["legacy_compatible"] is False
        assert snapshot["applied_rule_ids"]  # 实际应用的规则 ID 集合非空
        assert len(snapshot["applied_rules"]) >= 1  # 完整规则快照

        # 保存后修改当前设置：汇率 + 新增规则 + 禁用原规则
        settings = temp_context.settings_service.load()
        settings["exchange_rate_usd_to_rmb"] = 6.5
        settings.setdefault("profit_rules", [])
        settings["profit_rules"].append(asdict(_income_rule("new_rule", "新规则", 100.0, 5.0)))
        temp_context.settings_service.save(settings)

        # 重新打开：界面结果必须与保存时完全一致，不静默按当前设置重算
        page.load_record_payload(record_id)
        b2 = page.profit_binder
        assert b2._exchange_rate == pytest.approx(RATE)
        assert b2.txt_na_price_usd.value() == pytest.approx(30.0)
        assert b2.txt_act_price_usd.value() == pytest.approx(saved_act_price)
        assert b2.txt_na_profit_rmb.value() == pytest.approx(saved_na_profit, abs=0.02)
        assert b2.txt_act_profit_rmb.value() == pytest.approx(saved_act_profit, abs=0.02)
        assert b2.spin_profit_rate.value() == pytest.approx(saved_rate, abs=0.02)

        # 用户主动重算（编辑无活动售价）→ 使用当前设置，属当前推算
        b2.txt_na_price_usd.setValue(31.0)
        assert b2._exchange_rate == pytest.approx(6.5)
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_real_page_legacy_record_open_no_fabricated_activity(qapp, temp_context):
    from profit_accounting_26.ui.pages import CalculationPage

    legacy_record = {
        "product_name": "旧记录",
        "layers": {
            "calculated": {
                "sale_price_usd": 25.0,
                "exchange_rate": 7.0,
                "profit_rmb": 30.0,
                "calculation_cost_rmb": 145.0,
                "reserve_percent": 0,
                "profit_rate_percent": 20.0,
                "selected_profit_rule_id": "",
            }
        },
        "shein_quote_usd": 22.0,
    }
    record_id = temp_context.record_service.save(legacy_record, images=[])

    page = CalculationPage(temp_context)
    try:
        page.load_record_payload(record_id)
        b = page.profit_binder
        # 只恢复无活动历史字段
        assert b.txt_na_price_usd.value() == pytest.approx(25.0)
        assert b.txt_na_profit_rmb.value() == pytest.approx(30.0)
        # 活动场景保持为空，不伪造活动历史
        assert b.txt_act_price_usd.value() == 0.0
        assert b.txt_act_profit_rmb.value() == 0.0
        assert b.lbl_act_status.text() == ""
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_real_page_legacy_record_user_recalc_is_current_not_history(qapp, temp_context):
    """旧记录打开后用户主动重算，必须属当前推算，不属于历史快照。"""
    from profit_accounting_26.ui.pages import CalculationPage

    legacy_record = {
        "product_name": "旧记录2",
        "layers": {
            "calculated": {
                "sale_price_usd": 25.0,
                "exchange_rate": 7.0,
                "profit_rmb": 30.0,
                "calculation_cost_rmb": 145.0,
            }
        },
    }
    record_id = temp_context.record_service.save(legacy_record, images=[])

    page = CalculationPage(temp_context)
    try:
        page.load_record_payload(record_id)
        b = page.profit_binder
        assert b._snapshot_display_mode is True
        # 用户主动编辑 → 退出快照显示模式，按当前设置重算
        b.txt_na_price_usd.setValue(26.0)
        assert b._snapshot_display_mode is False
        assert b._no_activity_price_usd == pytest.approx(26.0)
        assert b._exchange_rate == pytest.approx(RATE)  # 当前设置汇率
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_snapshot_fields_include_full_rule_snapshot_and_legacy_flag(qapp, binder):
    rules = (
        _income_rule("r1", "补贴A", 29.0, 2.99),
        _income_rule("r2", "补贴B", 5.0, 1.00),  # 30 USD 下不命中，但应在完整快照中
    )
    binder.set_rules(rules)
    binder.set_calculation_cost(100.0)
    binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
    binder.txt_na_price_usd.setValue(30.0)
    binder.cmb_rule.setCurrentIndex(binder.cmb_role_find(ALL_ENABLED_RULES_ID))
    binder._refresh_all()

    snap = binder.export_profit_scenarios()
    assert snap["exchange_rate"] == pytest.approx(RATE)
    assert snap["legacy_compatible"] is False
    assert set(snap["applied_rule_ids"]) == {"r1", "r2"}
    # 完整规则快照包含未命中的 r2
    snap_ids = {r["id"] for r in snap["applied_rules"]}
    assert snap_ids == {"r1", "r2"}
    assert snap["selected_rule_id"] == ALL_ENABLED_RULES_ID


# ---------------------------------------------------------------------------
# 修正 4：版本标题（真实 MainWindow）
# ---------------------------------------------------------------------------


def test_real_main_window_title_is_261_from_ui(qapp, temp_context):
    from profit_accounting_26.ui.main_window import MainWindow

    window = MainWindow(temp_context)
    try:
        assert window.windowTitle() == "微智能利润管理软件 2.6.1"
    finally:
        window.close()
        qapp.processEvents()
