"""本轮唯一主软件业务改动：三项利润字段“明确保存后沿用”默认值机制。

范围严格限定：``spinPromotionReserve`` / ``txtListPriceProfitRate`` /
``spinProfitRate``。

覆盖（任务书第十四节 A 组 8 项 + 共享核心 20-23）：
1. 仅编辑不保存 → 默认值不变；
2. 主软件明确保存成功后 → 3 项默认值写入 settings（向后兼容新键）；
3. 重启（新页面/新窗口）→ 恢复保存值；
4. 主软件清空 → 恢复保存值；
5. Quick 启动 → 读取同一套保存值；
6. Quick 清空 → 恢复保存值；
7. Quick 临时修改 → 不写回默认值；
8. 旧 settings 无新键 → 沿用现有初始默认（15%/25%）。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os
from dataclasses import asdict

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.application.profit_defaults import (  # noqa: E402
    ACTIVITY_RATE_DEFAULT_KEY,
    LIST_PRICE_RATE_DEFAULT_KEY,
    RESERVE_DEFAULT_KEY,
)
from profit_accounting_26.ui.pages import CalculationPage  # noqa: E402
from profit_accounting_26.ui.quick_calculator_window import QuickCalculatorWindow  # noqa: E402


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _install_forwarder(context: AppContext) -> None:
    settings = context.settings_service.load()
    forwarder = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    settings["forwarders"] = [asdict(forwarder)]
    settings["selected_forwarder_id"] = forwarder.id
    settings["exchange_rate_usd_to_rmb"] = 7.2
    context.settings_service.save(settings)


def _make_saveable_main_page(context: AppContext) -> CalculationPage:
    """构造可保存的主软件页面（有货代、尺寸、成本）。"""
    _install_forwarder(context)
    page = CalculationPage(context)
    page._updating = False
    for key, value in (("length", 30.0), ("width", 20.0), ("height", 10.0), ("weight", 500.0)):
        page.conservative_fields[key].setValue(value)
    page.product_cost.setValue(66.8)
    page.recalculate()
    return page


def _silence_dialogs(monkeypatch) -> None:
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(qw.QMessageBox, "critical", lambda *a, **k: None)


def _defaults_on_disk(context: AppContext) -> dict:
    settings = context.settings_service.load()
    return {
        RESERVE_DEFAULT_KEY: settings.get(RESERVE_DEFAULT_KEY),
        ACTIVITY_RATE_DEFAULT_KEY: settings.get(ACTIVITY_RATE_DEFAULT_KEY),
        LIST_PRICE_RATE_DEFAULT_KEY: settings.get(LIST_PRICE_RATE_DEFAULT_KEY),
    }


# ==================================================================
# A1-A2. 保存才生效 / 保存成功写入
# ==================================================================


def test_editing_without_save_does_not_become_default(qapp, temp_context):
    """A1：仅编辑不保存 → 默认值不变（settings 不出现新键）。"""
    page = _make_saveable_main_page(temp_context)
    try:
        binder = page.profit_binder
        binder.spin_reserve.setValue(18.0)
        binder.spin_profit_rate.setValue(32.0)
        assert binder.spin_reserve.value() == pytest.approx(18.0)
        assert binder.spin_profit_rate.value() == pytest.approx(32.0)
        # 没有保存 → settings 无新键
        assert all(value is None for value in _defaults_on_disk(temp_context).values())
    finally:
        page.deleteLater()


def test_main_save_success_writes_three_defaults(qapp, temp_context, monkeypatch):
    """A2：主软件明确保存成功后，3 项默认值写入 settings。"""
    _silence_dialogs(monkeypatch)
    page = _make_saveable_main_page(temp_context)
    try:
        binder = page.profit_binder
        binder.spin_reserve.setValue(18.0)
        binder.spin_profit_rate.setValue(32.0)
        page.save_record()
        defaults = _defaults_on_disk(temp_context)
        assert defaults[RESERVE_DEFAULT_KEY] == pytest.approx(18.0)
        assert defaults[ACTIVITY_RATE_DEFAULT_KEY] == pytest.approx(32.0)
        # 标价利率以保存时的实际值为准（若被 driver 派生则存派生值）
        assert defaults[LIST_PRICE_RATE_DEFAULT_KEY] == pytest.approx(
            binder.txt_list_price_rate.value()
        )
    finally:
        page.deleteLater()


# ==================================================================
# A3-A4. 主软件重启 / 清空恢复
# ==================================================================


def test_main_restart_restores_saved_defaults(qapp, temp_context, monkeypatch):
    """A3：保存后重启（新页面）→ 恢复保存值。"""
    _silence_dialogs(monkeypatch)
    page = _make_saveable_main_page(temp_context)
    try:
        page.profit_binder.spin_reserve.setValue(20.0)
        page.profit_binder.spin_profit_rate.setValue(35.0)
        page.save_record()
    finally:
        page.deleteLater()
    reopened = CalculationPage(temp_context)
    try:
        assert reopened.profit_binder.spin_reserve.value() == pytest.approx(20.0)
        assert reopened.profit_binder.spin_profit_rate.value() == pytest.approx(35.0)
    finally:
        reopened.deleteLater()


def test_main_clear_restores_saved_defaults(qapp, temp_context, monkeypatch):
    """A4：保存后主软件清空 → 恢复保存值。"""
    _silence_dialogs(monkeypatch)
    page = _make_saveable_main_page(temp_context)
    try:
        binder = page.profit_binder
        binder.spin_reserve.setValue(22.0)
        binder.spin_profit_rate.setValue(38.0)
        page.save_record()
        # 保存后清空
        page.clear_new()
        assert page.profit_binder.spin_reserve.value() == pytest.approx(22.0)
        assert page.profit_binder.spin_profit_rate.value() == pytest.approx(38.0)
    finally:
        page.deleteLater()


# ==================================================================
# A5-A7. Quick 读取同一默认值 / 不写回
# ==================================================================


def test_quick_startup_reads_saved_defaults(qapp, temp_context, monkeypatch):
    """A5：Quick 启动读取主软件保存的同一套默认值。"""
    _silence_dialogs(monkeypatch)
    page = _make_saveable_main_page(temp_context)
    try:
        page.profit_binder.spin_reserve.setValue(21.0)
        page.profit_binder.spin_profit_rate.setValue(36.0)
        page.save_record()
    finally:
        page.deleteLater()
    window = QuickCalculatorWindow(temp_context)
    try:
        assert window.profit_binder.spin_reserve.value() == pytest.approx(21.0)
        assert window.profit_binder.spin_profit_rate.value() == pytest.approx(36.0)
    finally:
        window.close()
        window.deleteLater()


def test_quick_clear_restores_saved_defaults(qapp, temp_context, monkeypatch):
    """A6：Quick 清空 → 恢复主软件保存的默认值。"""
    _silence_dialogs(monkeypatch)
    page = _make_saveable_main_page(temp_context)
    try:
        page.profit_binder.spin_reserve.setValue(19.0)
        page.profit_binder.spin_profit_rate.setValue(33.0)
        page.save_record()
    finally:
        page.deleteLater()
    window = QuickCalculatorWindow(temp_context)
    try:
        window.profit_binder.spin_reserve.setValue(5.0)
        window.profit_binder.spin_profit_rate.setValue(9.0)
        window.clear_new()
        assert window.profit_binder.spin_reserve.value() == pytest.approx(19.0)
        assert window.profit_binder.spin_profit_rate.value() == pytest.approx(33.0)
    finally:
        window.close()
        window.deleteLater()


def test_quick_temp_edits_never_write_defaults(qapp, temp_context):
    """A7：Quick 临时修改这 3 项不写回默认值（Quick 没有保存商品动作）。"""
    _install_forwarder(temp_context)
    before = _defaults_on_disk(temp_context)
    window = QuickCalculatorWindow(temp_context)
    try:
        window.profit_binder.spin_reserve.setValue(3.0)
        window.profit_binder.spin_profit_rate.setValue(4.0)
        window.profit_binder.txt_list_price_rate.setValue(5.0)
    finally:
        window.close()
        window.deleteLater()
    assert _defaults_on_disk(temp_context) == before


# ==================================================================
# A8. 旧 settings 兼容：无新键沿用现有初始默认
# ==================================================================


def test_no_saved_defaults_falls_back_to_existing_defaults(qapp, temp_context):
    """A8：旧 settings 无新键 → 主软件与 Quick 都沿用现有初始默认（15%/25%）。"""
    assert all(value is None for value in _defaults_on_disk(temp_context).values())
    page = _make_saveable_main_page(temp_context)
    try:
        assert page.profit_binder.spin_reserve.value() == pytest.approx(15.0)
        assert page.profit_binder.spin_profit_rate.value() == pytest.approx(25.0)
        page.clear_new()
        assert page.profit_binder.spin_reserve.value() == pytest.approx(15.0)
        assert page.profit_binder.spin_profit_rate.value() == pytest.approx(25.0)
    finally:
        page.deleteLater()
    window = QuickCalculatorWindow(temp_context)
    try:
        assert window.profit_binder.spin_reserve.value() == pytest.approx(15.0)
        assert window.profit_binder.spin_profit_rate.value() == pytest.approx(25.0)
        window.clear_new()
        assert window.profit_binder.spin_reserve.value() == pytest.approx(15.0)
        assert window.profit_binder.spin_profit_rate.value() == pytest.approx(25.0)
    finally:
        window.close()
        window.deleteLater()
