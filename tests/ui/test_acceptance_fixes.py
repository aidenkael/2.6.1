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


# ===========================================================================
# 第二轮定点修正：加载保护 / 系统成本联动 / SHEIN 核价 / 旧记录保存 / 状态提示
# ===========================================================================


def _fill_and_save_record(page, monkeypatch, na_price=30.0, cost=35.0):
    """填充并保存一条带双场景快照的记录，返回 (binder, record_id)。"""
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    page.product_cost.setValue(cost)
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
    b._refresh_all()
    page.save_record()
    assert page.record_id
    return b, page.record_id


# ---------------------------------------------------------------------------
# 修正 1+：加载保护状态 _loading_record
# ---------------------------------------------------------------------------


class TestLoadingRecordProtection:
    """验证 _loading_record 保护机制。"""

    def test_loading_record_flag_reset_after_load(self, qapp, temp_context, monkeypatch):
        """load_record_payload 完成后 _loading_record 必须为 False。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            _fill_and_save_record(page, monkeypatch)
            rid = page.record_id
            page.profit_binder._loading_record = True  # 模拟异常残留
            page.load_record_payload(rid)
            assert page.profit_binder._loading_record is False
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_loading_record_false_on_exception(self, qapp, temp_context, monkeypatch):
        """load_record_payload 异常时 _loading_record 通过 finally 正确复位。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            _fill_and_save_record(page, monkeypatch)
            rid = page.record_id
            # 模拟 _select_package 抛异常
            original = page._select_package
            def boom(*a, **k):
                raise RuntimeError("test")
            page._select_package = boom
            try:
                page.load_record_payload(rid)
            except RuntimeError:
                pass
            finally:
                page._select_package = original
            assert page.profit_binder._loading_record is False
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_internal_recalculate_does_not_exit_snapshot(self, qapp, temp_context, monkeypatch):
        """加载记录时内部 recalculate 不退出快照。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            b, rid = _fill_and_save_record(page, monkeypatch)
            saved_rate = b._exchange_rate
            page.load_record_payload(rid)
            b2 = page.profit_binder
            # 加载后仍处于快照模式
            assert b2._snapshot_display_mode is True
            assert b2._loading_record is False
            # 汇率仍为保存时汇率，未被当前设置覆盖
            assert b2._exchange_rate == pytest.approx(saved_rate)
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_system_cost_change_after_load_exits_snapshot(self, qapp, temp_context, monkeypatch):
        """加载完成后修改系统成本会退出快照。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            b, rid = _fill_and_save_record(page, monkeypatch)
            saved_na_profit = b.txt_na_profit_rmb.value()
            page.load_record_payload(rid)
            b2 = page.profit_binder
            assert b2._snapshot_display_mode is True
            # 模拟加载完成后系统成本变化
            b2.set_calculation_cost(999.99)
            assert b2._snapshot_display_mode is False
            assert b2._calculation_total_cost_rmb == pytest.approx(999.99)
            # 利润已按新成本重算，与保存时不同
            assert b2.txt_na_profit_rmb.value() != pytest.approx(saved_na_profit, abs=0.01)
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_tiny_float_diff_does_not_exit_snapshot(self, qapp, binder):
        """即使加载重算成本存在极小浮点差异，_loading_record=True 也不退出快照。"""
        binder.set_calculation_cost(100.0)
        binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        binder.txt_na_price_usd.setValue(30.0)
        binder._snapshot_display_mode = True
        binder._loading_record = True
        # 极小浮点差异
        binder.set_calculation_cost(100.0000001)
        assert binder._snapshot_display_mode is True
        assert binder._loading_record is True
        # 加载结束
        binder._loading_record = False
        # 加载结束后微小差异仍不退出（因为 _exit 只在 _loading_record=False 时触发）
        binder.set_calculation_cost(200.0)
        assert binder._snapshot_display_mode is False


# ---------------------------------------------------------------------------
# 修正 2+：SHEIN 核价编辑不退出快照、不重算利润
# ---------------------------------------------------------------------------


class TestSheinQuoteEditBehavior:
    """验证 SHEIN 核价编辑行为。"""

    def test_shein_edit_does_not_exit_snapshot(self, qapp, temp_context, monkeypatch):
        """保存记录后改汇率规则再打开，仅修改核价，两个场景售价/利润/规则状态不变。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            b, rid = _fill_and_save_record(page, monkeypatch, na_price=30.0)
            saved_na_price = b.txt_na_price_usd.value()
            saved_act_price = b.txt_act_price_usd.value()
            saved_na_profit = b.txt_na_profit_rmb.value()
            saved_act_profit = b.txt_act_profit_rmb.value()
            saved_na_status = b.lbl_na_status.text()
            saved_act_status = b.lbl_act_status.text()

            # 修改当前设置：汇率 + 新增规则
            settings = temp_context.settings_service.load()
            settings["exchange_rate_usd_to_rmb"] = 6.5
            settings.setdefault("profit_rules", [])
            settings["profit_rules"].append(asdict(_income_rule("new_r", "新规则", 100.0, 5.0)))
            temp_context.settings_service.save(settings)

            # 重新打开
            page.load_record_payload(rid)
            b2 = page.profit_binder
            assert b2._snapshot_display_mode is True

            # 仅修改 SHEIN 核价
            b2.txt_shein_usd.setValue(28.0)

            # 两个场景售价、利润、规则状态全部保持不变
            assert b2.txt_na_price_usd.value() == pytest.approx(saved_na_price)
            assert b2.txt_act_price_usd.value() == pytest.approx(saved_act_price)
            assert b2.txt_na_profit_rmb.value() == pytest.approx(saved_na_profit, abs=0.02)
            assert b2.txt_act_profit_rmb.value() == pytest.approx(saved_act_profit, abs=0.02)
            assert b2.lbl_na_status.text() == saved_na_status
            assert b2.lbl_act_status.text() == saved_act_status
            # 仍在快照模式
            assert b2._snapshot_display_mode is True
            # SHEIN RMB 已按保存时汇率换算
            assert b2.txt_shein_rmb.value() == pytest.approx(28.0 * RATE, abs=0.02)
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_shein_edit_does_not_change_driver(self, qapp, binder):
        """修改 SHEIN 核价不改变当前 driver。"""
        binder.set_calculation_cost(100.0)
        binder._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        binder.txt_na_price_usd.setValue(30.0)
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        driver_before = binder._profit_driver
        binder.txt_shein_usd.setValue(25.0)
        assert binder._profit_driver == driver_before
        assert binder._snapshot_display_mode is True


# ---------------------------------------------------------------------------
# 修正 3+：旧记录保存逻辑
# ---------------------------------------------------------------------------


class TestLegacyRecordSaveLogic:
    """验证旧记录保存逻辑。"""

    def _make_legacy_record(self, temp_context):
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
        return temp_context.record_service.save(legacy_record, images=[])

    def test_legacy_no_modify_save_keeps_empty_activity(self, qapp, temp_context, monkeypatch):
        """打开旧记录后不做任何修改直接保存，活动场景仍为空。"""
        from profit_accounting_26.ui.pages import CalculationPage

        rid = self._make_legacy_record(temp_context)
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            assert b._snapshot_legacy is True
            assert b._legacy_exited is False
            # 直接导出（模拟保存）
            snap = b.export_profit_scenarios()
            assert snap["legacy_compatible"] is True
            act = snap.get("activity", {})
            assert act.get("sale_price_usd", 0) == 0.0
            assert act.get("profit_rmb", 0) == 0.0
            assert act.get("profit_usd", 0) == 0.0
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_legacy_shein_only_save_keeps_empty_activity(self, qapp, temp_context, monkeypatch):
        """打开旧记录后只修改 SHEIN 核价再保存，活动场景仍为空。"""
        from profit_accounting_26.ui.pages import CalculationPage

        rid = self._make_legacy_record(temp_context)
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            # 只修改 SHEIN 核价
            b.txt_shein_usd.setValue(20.0)
            assert b._legacy_exited is False
            snap = b.export_profit_scenarios()
            assert snap["legacy_compatible"] is True
            act = snap.get("activity", {})
            assert act.get("sale_price_usd", 0) == 0.0
            assert act.get("profit_rmb", 0) == 0.0
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_legacy_modify_reserve_exits_to_current(self, qapp, temp_context, monkeypatch):
        """打开旧记录后修改活动预留，转为当前推算并生成双场景。"""
        from profit_accounting_26.ui.pages import CalculationPage

        rid = self._make_legacy_record(temp_context)
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            # 修改活动预留
            b.spin_reserve.setValue(10.0)
            assert b._legacy_exited is True
            assert b._snapshot_display_mode is False
            snap = b.export_profit_scenarios()
            assert snap["legacy_compatible"] is False
            act = snap.get("activity", {})
            assert act.get("sale_price_usd", 0) > 0.0
            assert act.get("profit_rmb", 0) != 0.0
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_legacy_system_cost_change_exits_to_current(self, qapp, temp_context, monkeypatch):
        """打开旧记录后修改系统成本，转为当前推算。"""
        from profit_accounting_26.ui.pages import CalculationPage

        rid = self._make_legacy_record(temp_context)
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            b.set_calculation_cost(200.0)
            assert b._legacy_exited is True
            assert b._snapshot_display_mode is False
            snap = b.export_profit_scenarios()
            assert snap["legacy_compatible"] is False
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_legacy_save_reopen_status_consistent(self, qapp, temp_context, monkeypatch):
        """旧记录退出 legacy 后保存重开，状态和标记一致。"""
        from profit_accounting_26.ui.pages import CalculationPage
        import PySide6.QtWidgets as qw

        rid = self._make_legacy_record(temp_context)
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            b.spin_reserve.setValue(10.0)
            assert b._legacy_exited is True
            # 填充必要数据后保存
            page.product_cost.setValue(35.0)
            page.domestic_shipping.setValue(5.0)
            page.normal_fields["length"].setValue(25.0)
            page.normal_fields["width"].setValue(18.0)
            page.normal_fields["height"].setValue(6.0)
            page.normal_fields["weight"].setValue(320.0)
            page.recalculate()
            monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
            page.save_record()
            rid2 = page.record_id

            # 重新打开
            page.load_record_payload(rid2)
            b2 = page.profit_binder
            assert b2._snapshot_legacy is False
            assert b2._legacy_exited is False
            assert b2._snapshot_display_mode is True
            snap = b2.export_profit_scenarios()
            assert snap["legacy_compatible"] is False
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 修正 4+：快照状态提示
# ---------------------------------------------------------------------------


class TestSnapshotStatusLabel:
    """验证快照状态提示。"""

    def test_status_history_snapshot(self, qapp, binder):
        """历史快照状态文案正确。"""
        binder.set_calculation_cost(100.0)
        binder.txt_na_price_usd.setValue(30.0)
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = False
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert binder._current_snapshot_status() == "历史快照"
        tip = binder.lbl_conclusion.toolTip()
        assert "历史快照" in tip

    def test_status_legacy(self, qapp, binder):
        """旧记录兼容数据状态文案正确。"""
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = True
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert binder._current_snapshot_status() == "旧记录兼容数据"
        tip = binder.lbl_conclusion.toolTip()
        assert "旧记录兼容数据" in tip

    def test_status_current(self, qapp, binder):
        """当前推算状态文案正确。"""
        binder._snapshot_display_mode = False
        binder._snapshot_loaded = False
        binder._snapshot_legacy = False
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert binder._current_snapshot_status() == "当前推算（非历史快照）"

    def test_status_transitions_on_exit(self, qapp, binder):
        """退出快照后状态从历史快照转为当前推算。"""
        binder.set_calculation_cost(100.0)
        binder.txt_na_price_usd.setValue(30.0)
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = False
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert "历史快照" in binder.lbl_conclusion.toolTip()
        # 退出快照
        binder._exit_snapshot_mode()
        assert binder._current_snapshot_status() == "当前推算（非历史快照）"
        assert "当前推算" in binder.lbl_conclusion.toolTip()


# ===========================================================================
# 第三轮定点修正：payload 数据一致 / 旧记录原样保存 / tooltip 去重
# ===========================================================================


# ---------------------------------------------------------------------------
# 修正 1：历史快照保存数据一致（build_record_payload 不混入当前数据）
# ---------------------------------------------------------------------------


class TestPayloadDataConsistency:
    """验证快照/legacy 状态下 build_record_payload 数据一致。"""

    def test_snapshot_payload_uses_snapshot_values(self, qapp, temp_context, monkeypatch):
        """保存记录后改汇率/物流，打开历史记录直接保存，layers 字段来自同一快照。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            b, rid = _fill_and_save_record(page, monkeypatch, na_price=30.0, cost=35.0)
            saved_rate = b._exchange_rate
            saved_cost = b._calculation_total_cost_rmb

            # 修改当前汇率
            settings = temp_context.settings_service.load()
            settings["exchange_rate_usd_to_rmb"] = 6.5
            temp_context.settings_service.save(settings)

            # 重新打开
            page.load_record_payload(rid)
            b2 = page.profit_binder
            assert b2.is_in_snapshot_mode() is True

            # 直接 build_record_payload（模拟保存）
            payload = page.build_record_payload()
            ps = payload["profit_scenarios"]
            calc = payload["layers"]["calculated"]
            adopted = payload["layers"]["adopted"]

            # layers.calculated.exchange_rate 来自快照，不是当前 settings
            assert calc["exchange_rate"] == pytest.approx(saved_rate)
            # layers.calculated.system_cost_rmb 来自快照
            assert calc["system_cost_rmb"] == pytest.approx(ps["calculation_total_cost_rmb"])
            # layers.adopted.calculation_cost_rmb 来自快照
            assert adopted["calculation_cost_rmb"] == pytest.approx(ps["calculation_total_cost_rmb"])
            # sale_price / profit / profit_rate 来自同一 profit_scenarios
            assert calc["sale_price_usd"] == pytest.approx(ps["no_activity"]["sale_price_usd"])
            assert calc["profit_rmb"] == pytest.approx(ps["no_activity"]["profit_rmb"])
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_current_mode_payload_uses_current_values(self, qapp, temp_context, monkeypatch):
        """当前推算模式下 build_record_payload 使用当前 settings 和 system_cost。"""
        from profit_accounting_26.ui.pages import CalculationPage

        page = CalculationPage(temp_context)
        try:
            _fill_and_save_record(page, monkeypatch, na_price=30.0, cost=35.0)
            current_rate = float(page.settings.get("exchange_rate_usd_to_rmb", 7.2))
            current_cost = page.current_system_cost

            # 不打开历史记录，直接 build payload（当前模式）
            assert page.profit_binder.is_in_snapshot_mode() is False
            payload = page.build_record_payload()
            calc = payload["layers"]["calculated"]
            assert calc["exchange_rate"] == pytest.approx(current_rate)
            assert calc["system_cost_rmb"] == pytest.approx(current_cost)
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 修正 2：旧记录未退出兼容状态时原样保存历史值
# ---------------------------------------------------------------------------


class TestLegacyOriginalValuesPreserved:
    """验证旧记录原样保存，不重新推导。"""

    def test_legacy_inconsistent_profit_preserved(self, qapp, temp_context):
        """故意不满足 售价×汇率−成本=旧利润 的旧记录，打开后直接保存旧利润保持原值。"""
        # 构造一个利润值与售价/成本/汇率不一致的旧记录
        # 25 USD × 7.0 = 175 RMB, 成本 145 RMB, 正确利润应为 30 RMB
        # 但我们故意写入利润 50 RMB（不一致）
        legacy_record = {
            "product_name": "不一致旧记录",
            "layers": {
                "calculated": {
                    "sale_price_usd": 25.0,
                    "exchange_rate": 7.0,
                    "profit_rmb": 50.0,  # 故意不一致（应为 30.0）
                    "calculation_cost_rmb": 145.0,
                    "reserve_percent": 0,
                    "profit_rate_percent": 34.48,
                    "selected_profit_rule_id": "",
                }
            },
            "shein_quote_usd": 22.0,
        }
        rid = temp_context.record_service.save(legacy_record, images=[])

        from profit_accounting_26.ui.pages import CalculationPage
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            assert b._snapshot_legacy is True
            assert b._legacy_exited is False

            # 直接导出（模拟保存）
            snap = b.export_profit_scenarios()
            na = snap.get("no_activity", {})
            # 旧利润原样保持 50.0，不被重新计算为 30.0
            assert na["profit_rmb"] == pytest.approx(50.0)
            assert na["sale_price_usd"] == pytest.approx(25.0)
            assert na["sale_price_rmb"] == pytest.approx(175.0)
            # 活动场景为空
            act = snap.get("activity", {})
            assert act["sale_price_usd"] == 0.0
            assert act["profit_rmb"] == 0.0
            assert snap["legacy_compatible"] is True
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_legacy_shein_change_preserves_original_profit(self, qapp, temp_context):
        """旧记录打开后只改核价再保存，旧利润仍保持原值。"""
        legacy_record = {
            "product_name": "旧记录核价测试",
            "layers": {
                "calculated": {
                    "sale_price_usd": 25.0,
                    "exchange_rate": 7.0,
                    "profit_rmb": 50.0,  # 故意不一致
                    "calculation_cost_rmb": 145.0,
                }
            },
            "shein_quote_usd": 22.0,
        }
        rid = temp_context.record_service.save(legacy_record, images=[])

        from profit_accounting_26.ui.pages import CalculationPage
        page = CalculationPage(temp_context)
        try:
            page.load_record_payload(rid)
            b = page.profit_binder
            # 只修改 SHEIN 核价
            b.txt_shein_usd.setValue(18.0)
            assert b._legacy_exited is False

            snap = b.export_profit_scenarios()
            na = snap.get("no_activity", {})
            assert na["profit_rmb"] == pytest.approx(50.0)  # 原值不变
            assert snap["shein_quote_usd"] == pytest.approx(18.0)  # 核价已更新
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 修正 3：状态 tooltip 重复累积
# ---------------------------------------------------------------------------


class TestTooltipNoAccumulation:
    """验证状态 tooltip 不重复累积。"""

    def test_five_refreshes_one_status_line(self, qapp, binder):
        """连续刷新 5 次，tooltip 中状态行只有 1 条。"""
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = False
        binder._legacy_exited = False
        for _ in range(5):
            binder._update_snapshot_status_label()
        tip = binder.lbl_conclusion.toolTip()
        count = tip.count("[利润区状态]")
        assert count == 1

    def test_history_to_current_no_old_status(self, qapp, binder):
        """历史快照 → 当前推算后，tooltip 不再包含'历史快照'状态行。"""
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = False
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert "[利润区状态] 历史快照" in binder.lbl_conclusion.toolTip()
        # 退出快照
        binder._exit_snapshot_mode()
        tip = binder.lbl_conclusion.toolTip()
        assert "[利润区状态] 历史快照" not in tip
        assert "[利润区状态] 当前推算" in tip

    def test_legacy_to_current_no_old_status(self, qapp, binder):
        """旧记录兼容 → 当前推算后，tooltip 不再包含'旧记录兼容数据'。"""
        binder._snapshot_display_mode = True
        binder._snapshot_loaded = True
        binder._snapshot_legacy = True
        binder._legacy_exited = False
        binder._update_snapshot_status_label()
        assert "旧记录兼容数据" in binder.lbl_conclusion.toolTip()
        # 退出 legacy
        binder._exit_snapshot_mode()
        tip = binder.lbl_conclusion.toolTip()
        assert "旧记录兼容数据" not in tip
        assert "当前推算" in tip
