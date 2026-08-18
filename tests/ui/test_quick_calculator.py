"""UU测算（quick calculator）targeted tests —— 任务书第十一节 19 项。

覆盖：.ui 加载 / 单位硬规则 / 可编辑冻结表 / 尾程双币种 / 总成本手改不反推上游 /
物流引擎复用 / 总头程展示 / 系统成本数学等价 / 货代 1~3 显示与切换不落全局 /
五类 driver / 规则状态标签 / 清空 15%/25%/尾程/规则 / 独立启动不构造 MainWindow /
共享数据目录 / 蓝色图标 / 主软件零影响。

禁止真实 API / 浏览器 / 外部链接。
"""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel  # noqa: E402

from profit_accounting_26.application import AppContext, SettingsService  # noqa: E402
from profit_accounting_26.application.calculation_service import CalculationService  # noqa: E402
from profit_accounting_26.domain.models import PackageSpec  # noqa: E402
from profit_accounting_26.domain.rules import (  # noqa: E402
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.shared import resource_path  # noqa: E402
from profit_accounting_26.ui import app as main_app_module  # noqa: E402
from profit_accounting_26.ui.quick_calculator_window import (  # noqa: E402
    QUICK_ICON_RELATIVE,
    QuickCalculatorWindow,
)
from profit_accounting_26.ui.ui_loader import load_ui  # noqa: E402

_FORWARDER_NAMES = ("义乌货代", "深圳货代", "广州货代", "杭州货代", "成都货代", "武汉货代")


def _install_forwarders(context: AppContext, count: int) -> list:
    settings = context.settings_service.load()
    forwarders = []
    for index in range(count):
        name = _FORWARDER_NAMES[index % len(_FORWARDER_NAMES)]
        forwarder = SettingsService.new_forwarder(
            name, 80.0 + index * 20, 10.0 + index, 8000.0,
        )
        forwarders.append(asdict(forwarder))
    settings["forwarders"] = forwarders
    settings["selected_forwarder_id"] = forwarders[0]["id"]
    settings["exchange_rate_usd_to_rmb"] = 7.2
    context.settings_service.save(settings)
    return SettingsService.forwarders_from_settings(context.settings_service.load())


def _set_spec(page: QuickCalculatorWindow) -> None:
    page.spin_length.setValue(30.0)
    page.spin_width.setValue(20.0)
    page.spin_height.setValue(10.0)
    page.spin_weight.setValue(500.0)
    page.spin_domestic_cost.setValue(66.8)


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture
def page(qapp, temp_context):
    window = QuickCalculatorWindow(temp_context)
    yield window
    window.close()
    window.deleteLater()


# ==================================================================
# 1-2. .ui 加载 + 单位/币种硬规则
# ==================================================================


def test_ui_loads_with_existing_loader(qapp):
    """第1项：.ui 可由现有 QUiLoader 正常加载，窗口名固定 UU测算。"""
    window = load_ui("quick_calculator.ui")
    try:
        assert window.windowTitle() == "UU测算"
        assert window.findChild(QDoubleSpinBox, "spinConservativeLengthCm") is not None
        assert window.findChild(QDoubleSpinBox, "spinProfitRate") is not None
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize(
    ("spin_name", "unit_label", "unit_text"),
    [
        ("spinConservativeLengthCm", "unitQuickspinConservativeLengthCm", "cm"),
        ("spinConservativeWidthCm", "unitQuickspinConservativeWidthCm", "cm"),
        ("spinConservativeHeightCm", "unitQuickspinConservativeHeightCm", "cm"),
        ("spinConservativeWeightG", "unitQuickspinConservativeWeightG", "g"),
        ("spinQuickDomesticCostRmb", "currencyQuickDomesticRmb", "¥"),
        ("txtQuickFirstMileTotalRmb", "currencyQuickFirstMileRmb", "¥"),
        ("spinTailFreightRmb", "currencyTailRmb", "¥"),
        ("spinTailFreightUsd", "currencyTailUsd", "$"),
        ("txtCalculatedCostRmb", "currencyCalculatedCostRmb", "¥"),
        ("txtCalculatedCostUsd", "currencyCalculatedCostUsd", "$"),
        ("txtNoActivityPriceRmb", "noActivityPriceRmbSymbol", "¥"),
        ("txtNoActivityPriceUsd", "noActivityPriceUsdSymbol", "$"),
        ("txtNoActivityProfitRmb", "noActivityProfitRmbSymbol", "¥"),
        ("txtNoActivityProfitUsd", "noActivityProfitUsdSymbol", "$"),
        ("txtActivityPriceRmb", "activityPriceRmbSymbol", "¥"),
        ("txtActivityPriceUsd", "activityPriceUsdSymbol", "$"),
        ("txtActivityProfitRmb", "activityProfitRmbSymbol", "¥"),
        ("txtActivityProfitUsd", "activityProfitUsdSymbol", "$"),
        ("txtListPriceProfitRate", "unit_txtListPriceProfitRate", "%"),
        ("spinPromotionReserve", "unitPromotionReserve", "%"),
        ("spinProfitRate", "unitProfitRate", "%"),
    ],
)
def test_unit_labels_are_outside_spinboxes(qapp, spin_name, unit_label, unit_text):
    """第2项：cm/g/¥/$/% 都是输入框外 QLabel，QDoubleSpinBox prefix/suffix 为空。"""
    window = load_ui("quick_calculator.ui")
    try:
        spin = window.findChild(QDoubleSpinBox, spin_name)
        label = window.findChild(QLabel, unit_label)
        assert spin is not None and label is not None, (spin_name, unit_label)
        assert spin.prefix() == "" and spin.suffix() == ""
        assert label.text() == unit_text
    finally:
        window.close()
        window.deleteLater()


# ==================================================================
# 3. 可编辑 / 冻结表与主 CalculationBinder 一致
# ==================================================================

_FROZEN_SPINS = (
    "txtQuickFirstMileTotalRmb",
    "spinTailFreightRmb",
    "txtCalculatedCostUsd",
    "txtNoActivityPriceRmb",
    "txtNoActivityProfitUsd",
    "txtActivityPriceRmb",
    "txtActivityPriceUsd",
    "txtActivityProfitUsd",
)
_EDITABLE_SPINS = (
    "spinConservativeLengthCm",
    "spinConservativeWidthCm",
    "spinConservativeHeightCm",
    "spinConservativeWeightG",
    "spinQuickDomesticCostRmb",
    "spinTailFreightUsd",
    "txtCalculatedCostRmb",
    "txtNoActivityPriceUsd",
    "txtNoActivityProfitRmb",
    "txtListPriceProfitRate",
    "spinPromotionReserve",
    "txtActivityProfitRmb",
    "spinProfitRate",
)


def test_editable_frozen_contract(page):
    """第3项：冻结/可编辑表与主 CalculationBinder 一致（尾程 RMB 冻结，USD 可编辑）。"""
    for name in _FROZEN_SPINS:
        spin = page.findChild(QDoubleSpinBox, name)
        assert spin is not None and spin.isReadOnly(), name
    for name in _EDITABLE_SPINS:
        spin = page.findChild(QDoubleSpinBox, name)
        assert spin is not None and not spin.isReadOnly(), name
    assert page.findChild(QComboBox, "cmbProfitRule") is not None
    assert page.findChild(QLabel, "lblNoActivitySubsidyStatus") is not None
    assert page.findChild(QLabel, "lblActivitySubsidyStatus") is not None


def test_quick_window_compact_and_default_on_top(page):
    """§7/§8：顶层窗口固定 448×475（min == max 硬契约），默认置顶且可取消。"""
    from profit_accounting_26.ui.quick_calculator_window import (
        QUICK_WINDOW_HEIGHT,
        QUICK_WINDOW_WIDTH,
    )

    assert page.width() == QUICK_WINDOW_WIDTH == 448
    assert page.height() == QUICK_WINDOW_HEIGHT == 475
    assert page.minimumSize() == page.maximumSize()
    # 默认置顶（checkbox 默认勾选 + WindowStaysOnTopHint）
    assert page.chk_stay_on_top.isChecked() is True
    assert bool(page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is True
    # 取消置顶 → flag 移除
    page.chk_stay_on_top.setChecked(False)
    assert bool(page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is False
    # 重新勾选 → 恢复
    page.chk_stay_on_top.setChecked(True)
    assert bool(page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is True


def test_input_widths_compressed_to_about_six_digits(page):
    """§四：普通数字输入框宽度明显缩短（约 6 位数字显示宽度，≤ 90px）。"""
    for name in _EDITABLE_SPINS + _FROZEN_SPINS:
        spin = page.findChild(QDoubleSpinBox, name)
        assert spin is not None, name
        assert spin.width() <= 90, f"{name} width={spin.width()}"
    # 利润规则下拉保留规则名所需宽度
    combo = page.findChild(QComboBox, "cmbProfitRule")
    assert combo is not None and combo.width() >= 100


def _row_starvation_px(spin) -> int:
    """返回 spin 所在嵌套行布局被压缩的像素数（行最小需求 - 实际分配）。

    直接在外层布局中（非嵌套行）的控件返回 0（严格检查）。
    """
    host = spin.parentWidget()
    layout = host.layout() if host is not None else None
    if layout is None:
        return 0
    for index in range(layout.count()):
        row = layout.itemAt(index).layout()
        if row is not None and row.indexOf(spin) >= 0:
            allocated = layout.itemAt(index).geometry().width()
            return max(0, row.minimumSize().width() - allocated)
    return 0


def test_unit_symbols_tight_against_inputs(page):
    """§五：¥/$/cm/g/% 紧贴对应输入框（同一组间距 ≤ 5px），且是外部 QLabel。"""
    pairs = [
        ("spinConservativeLengthCm", "unitQuickspinConservativeLengthCm"),
        ("spinConservativeWidthCm", "unitQuickspinConservativeWidthCm"),
        ("spinConservativeHeightCm", "unitQuickspinConservativeHeightCm"),
        ("spinConservativeWeightG", "unitQuickspinConservativeWeightG"),
        ("spinQuickDomesticCostRmb", "currencyQuickDomesticRmb"),
        ("txtQuickFirstMileTotalRmb", "currencyQuickFirstMileRmb"),
        ("spinTailFreightRmb", "currencyTailRmb"),
        ("spinTailFreightUsd", "currencyTailUsd"),
        ("txtCalculatedCostRmb", "currencyCalculatedCostRmb"),
        ("txtCalculatedCostUsd", "currencyCalculatedCostUsd"),
        ("txtNoActivityPriceRmb", "noActivityPriceRmbSymbol"),
        ("txtNoActivityPriceUsd", "noActivityPriceUsdSymbol"),
        ("txtNoActivityProfitRmb", "noActivityProfitRmbSymbol"),
        ("txtNoActivityProfitUsd", "noActivityProfitUsdSymbol"),
        ("txtActivityPriceRmb", "activityPriceRmbSymbol"),
        ("txtActivityPriceUsd", "activityPriceUsdSymbol"),
        ("txtActivityProfitRmb", "activityProfitRmbSymbol"),
        ("txtActivityProfitUsd", "activityProfitUsdSymbol"),
        ("txtListPriceProfitRate", "unit_txtListPriceProfitRate"),
        ("spinPromotionReserve", "unitPromotionReserve"),
        ("spinProfitRate", "unitProfitRate"),
    ]
    page.show()
    try:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        for spin_name, label_name in pairs:
            spin = page.findChild(QDoubleSpinBox, spin_name)
            label = page.findChild(QLabel, label_name)
            assert spin is not None and label is not None, (spin_name, label_name)
            # 符号/单位在输入框左侧或右侧都允许：取两控件之间的净间距
            gap = max(spin.geometry().left(), label.geometry().left()) - min(
                spin.geometry().right(), label.geometry().right()
            )
            # 真实用户环境（Windows + Microsoft YaHei UI）下行宽恰好贴合（gap=2）；
            # offscreen/CI 平台的回退字体更宽，窗口固定 448 后行会被压缩，
            # 重叠量不得超过行压缩量（否则是真实布局缺陷而非字体差异）。
            starvation = _row_starvation_px(spin)
            assert gap >= -starvation, f"{spin_name} 与 {label_name} 间距 {gap}px"
            assert gap <= 5, f"{spin_name} 与 {label_name} 间距 {gap}px"
    finally:
        page.hide()


def test_no_widget_clipping_after_refit(page):
    """§十三：按 sizeHint 收紧后所有控件都在窗口内、无裁剪。"""
    page.show()
    try:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.processEvents()
        for name in _EDITABLE_SPINS + _FROZEN_SPINS:
            spin = page.findChild(QDoubleSpinBox, name)
            assert spin is not None
            assert spin.geometry().right() <= page.width(), name
            assert spin.geometry().bottom() <= page.height(), name
        assert page.findChild(QComboBox, "cmbProfitRule").geometry().right() <= page.width()
        assert page.btn_clear.geometry().right() <= page.width()
    finally:
        page.hide()


# ==================================================================
# 4-8. 尾程 / 总成本 / 物流链复用
# ==================================================================


def test_tail_fee_usd_drives_rmb(page):
    """第4项：尾程 USD 可编辑 → RMB 冻结结果（USD × 汇率）；RMB 不可反向驱动 USD。"""
    _install_forwarders(page.context, 1)
    rate = 7.2
    # USD → RMB 正向联动
    page.tail_fee_usd.setValue(6.0)
    assert page.tail_fee_rmb.value() == pytest.approx(round(6.0 * rate, 2), abs=0.001)
    # RMB 为 readOnly，不能反向驱动 USD
    assert page.tail_fee_rmb.isReadOnly()
    # 即使程序化 setValue(RMB)，USD 不变（无反向信号连接）
    page.tail_fee_rmb.setValue(50.0)
    assert page.tail_fee_usd.value() == pytest.approx(6.0, abs=0.001)


def test_total_cost_edit_does_not_reverse_engineer_upstream(page):
    """第5项：总成本 RMB 可编辑、USD 冻结；手改总成本不反推国内成本/货代/头程。"""
    _install_forwarders(page.context, 1)
    _set_spec(page)
    domestic_before = page.spin_domestic_cost.value()
    first_mile_before = page.txt_first_mile_total.value()
    cost_spin = page.findChild(QDoubleSpinBox, "txtCalculatedCostRmb")
    cost_spin.setValue(500.0)
    assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(500.0)
    assert page.spin_domestic_cost.value() == pytest.approx(domestic_before)
    assert page.txt_first_mile_total.value() == pytest.approx(first_mile_before)
    usd_spin = page.findChild(QDoubleSpinBox, "txtCalculatedCostUsd")
    assert usd_spin.isReadOnly()
    assert usd_spin.value() == pytest.approx(round(500.0 / 7.2, 2), abs=0.001)


def test_dims_use_existing_logistics_engine(page):
    """第6项：长宽高重量变化使用现有物流引擎重算。"""
    forwarders = _install_forwarders(page.context, 1)
    _set_spec(page)
    first_mile_before = page.txt_first_mile_total.value()
    assert first_mile_before > 0
    page.spin_weight.setValue(1000.0)
    first_mile_after = page.txt_first_mile_total.value()
    assert first_mile_after != pytest.approx(first_mile_before)
    service = CalculationService()
    quote = service.quote_all_forwarders(
        package=PackageSpec(length_cm=30.0, width_cm=20.0, height_cm=10.0, weight_g=1000.0),
        forwarders=forwarders,
        tail_fee_rmb=page.tail_fee_rmb.value(),
    )[forwarders[0].id]
    assert page.txt_first_mile_total.value() == pytest.approx(quote.weight_fee_rmb + quote.fixed_fee_rmb)


def test_first_mile_total_is_quote_weight_plus_fixed(page):
    """第7项：总头程 = quote.weight_fee_rmb + quote.fixed_fee_rmb 展示值。"""
    forwarders = _install_forwarders(page.context, 1)
    _set_spec(page)
    service = CalculationService()
    quote = service.quote_all_forwarders(
        package=PackageSpec(length_cm=30.0, width_cm=20.0, height_cm=10.0, weight_g=500.0),
        forwarders=forwarders,
        tail_fee_rmb=page.tail_fee_rmb.value(),
    )[forwarders[0].id]
    assert page.txt_first_mile_total.value() == pytest.approx(quote.weight_fee_rmb + quote.fixed_fee_rmb)


def test_system_cost_equivalent_to_main(page):
    """第8项：国内成本（商品成本+国内运费合并）+ 当前物流结果 = 主软件等价总成本。"""
    forwarders = _install_forwarders(page.context, 1)
    _set_spec(page)
    service = CalculationService()
    quote = service.quote_all_forwarders(
        package=PackageSpec(length_cm=30.0, width_cm=20.0, height_cm=10.0, weight_g=500.0),
        forwarders=forwarders,
        tail_fee_rmb=page.tail_fee_rmb.value(),
    )[forwarders[0].id]
    # 主软件：product_cost + domestic_shipping + quote.total_logistics_rmb；
    # 轻量：国内成本(合并) + quote.total_logistics_rmb —— 数学等价。
    main_equivalent = 66.8 + quote.total_logistics_rmb
    assert page.profit_binder._calculation_total_cost_rmb == pytest.approx(main_equivalent)


# ==================================================================
# 9-11. 货代 1~3 显示与切换
# ==================================================================


@pytest.mark.parametrize("count", [1, 2, 3])
def test_forwarder_buttons_show_exactly_count(qapp, temp_context, count):
    """第9项：1/2/3 个启用货代分别只显示 1/2/3 个按钮（isHidden 反映显式可见状态）。"""
    _install_forwarders(temp_context, count)
    window = QuickCalculatorWindow(temp_context)
    try:
        for index in range(3):
            assert window._forwarder_buttons[index].isHidden() == (index >= count)
    finally:
        window.close()
        window.deleteLater()


def test_forwarder_missing_slots_hidden_and_more_than_three_not_shown(qapp, temp_context):
    """第10项：不存在货代不显示占位；超过 3 个也只显示前 3 个。"""
    _install_forwarders(temp_context, 5)
    window = QuickCalculatorWindow(temp_context)
    try:
        visible = [button for button in window._forwarder_buttons if not button.isHidden()]
        assert len(visible) == 3
        assert all(button.text() for button in visible)
    finally:
        window.close()
        window.deleteLater()


def test_forwarder_switch_recalculates_without_global_save(page):
    """第11项：货代切换重算但不新增全局默认保存。"""
    _install_forwarders(page.context, 2)
    _set_spec(page)
    settings_before = page.context.settings_service.load()["selected_forwarder_id"]
    other = next(
        button for button in page._forwarder_buttons
        if str(button.property("forwarderId") or "") != page.selected_forwarder_id
    )
    cost_before = page.profit_binder._calculation_total_cost_rmb
    other.click()
    assert page.selected_forwarder_id == str(other.property("forwarderId") or "")
    # 重算发生：切换货代后头程/总成本变化
    assert page.profit_binder._calculation_total_cost_rmb != pytest.approx(cost_before)
    assert page.context.settings_service.load()["selected_forwarder_id"] == settings_before


# ==================================================================
# 12-13. CalculationBinder 五类 driver + 规则状态标签
# ==================================================================


def test_five_profit_drivers_reused(page):
    """第12项：CalculationBinder 五类 driver 行为与主软件一致（原样复用）。"""
    _install_forwarders(page.context, 1)
    _set_spec(page)
    binder = page.profit_binder
    binder.spin_profit_rate.setValue(30.0)
    assert binder._profit_driver == "profit_rate"
    binder.txt_na_price_usd.setValue(20.0)
    assert binder._profit_driver == "no_activity_price"
    assert binder.txt_na_price_usd.value() == pytest.approx(20.0)
    binder.txt_na_profit_rmb.setValue(50.0)
    assert binder._profit_driver == "no_activity_profit"
    binder.txt_list_price_rate.setValue(40.0)
    assert binder._profit_driver == "no_activity_profit_rate"
    binder.txt_act_profit_rmb.setValue(80.0)
    assert binder._profit_driver == "activity_profit"
    # 编辑谁谁成为 driver，其他字段由现有 Binder 反推（不复制公式）
    assert binder.txt_act_profit_rmb.value() == pytest.approx(80.0)


def _income_rule(rule_id, name, threshold, amount, currency="USD"):
    return AdjustmentRule(
        id=rule_id, name=name,
        condition_field="sale_price_usd", compare_op=CompareOp.LT,
        condition_value=threshold, direction=AdjustmentDirection.INCOME,
        adjustment_type=AdjustmentType.FIXED, adjustment_value=amount,
        currency=currency, enabled=True, archived=False,
    )


def test_rule_status_labels_reuse_existing_judgment(qapp, temp_context):
    """第13项：两个规则状态标签直接显示现有规则判断结果。"""
    _install_forwarders(temp_context, 1)
    settings = temp_context.settings_service.load()
    rule = _income_rule("R-QUICK", "低价补贴", 50.0, 10.0)
    settings["profit_rules"] = [asdict(rule)]
    settings["selected_profit_rule_id"] = rule.id
    temp_context.settings_service.save(settings)

    window = QuickCalculatorWindow(temp_context)
    try:
        _set_spec(window)
        binder = window.profit_binder
        # 无活动售价 30 USD（< 50 门槛）→ 规则已触发 +¥72.00（10 USD × 7.2）
        binder.txt_na_price_usd.setValue(30.0)
        assert "已触发" in binder.lbl_na_status.text()
        assert "+¥72.00" in binder.lbl_na_status.text()
        # 无规则参与时显示“无规则”
        binder.cmb_rule.setCurrentIndex(0)  # “不使用规则”
        assert binder.lbl_na_status.text() == "无规则"
    finally:
        window.close()
        window.deleteLater()


# ==================================================================
# 14-15. 清空
# ==================================================================


def test_clear_restores_15_and_25_and_keeps_tail_and_rule(page):
    """第14/15项：清空后 reserve=15%、activity profit rate=25%；
    尾程不恢复硬编码、利润规则沿用、不写历史。"""
    _install_forwarders(page.context, 1)
    _set_spec(page)
    tail_usd_before = page.tail_fee_usd.value()
    rule_id_before = page.profit_binder.selected_rule_id
    page.clear_new()
    assert page.spin_length.value() == 0
    assert page.spin_width.value() == 0
    assert page.spin_height.value() == 0
    assert page.spin_weight.value() == 0
    assert page.spin_domestic_cost.value() == 0
    assert page.profit_binder.spin_reserve.value() == pytest.approx(15.0)
    assert page.profit_binder.spin_profit_rate.value() == pytest.approx(25.0)
    assert page.tail_fee_usd.value() == pytest.approx(tail_usd_before)
    assert page.profit_binder.selected_rule_id == rule_id_before
    assert page.context.history_record_v2_service.list_v2() == []
    assert page.profit_binder._calculation_total_cost_rmb == 0.0


def test_quick_never_writes_settings(qapp, temp_context):
    """Quick 只读设置：尾程编辑/货代切换/清空都不写 settings.json（§10 最小处理）。"""
    _install_forwarders(temp_context, 2)
    settings_path = temp_context.paths.settings_path
    before = settings_path.read_bytes()
    window = QuickCalculatorWindow(temp_context)
    _set_spec(window)
    window.tail_fee_usd.setValue(6.0)
    window._forwarder_buttons[1].click()
    window.clear_new()
    window.close()
    window.deleteLater()
    assert settings_path.read_bytes() == before


# ==================================================================
# 16-18. 独立启动 / 共享数据目录 / 蓝色图标
# ==================================================================


def test_quick_startup_does_not_build_main_window(qapp, temp_context, monkeypatch):
    """第16项：Quick 启动不构造 MainWindow。"""
    import profit_accounting_26.ui.main_window as main_window_module

    def forbidden(*_args, **_kwargs):
        raise AssertionError("UU测算 启动不得构造 MainWindow")

    monkeypatch.setattr(main_window_module, "MainWindow", forbidden)
    from profit_accounting_26.ui.quick_calculator_app import build_quick_window

    app, window = build_quick_window(data_dir=temp_context.paths.data_dir)
    assert window is not None
    assert type(window).__name__ == "QuickCalculatorWindow"
    window.close()
    window.deleteLater()


def test_quick_shares_same_data_dir(qapp, temp_context):
    """第17项：Quick 与主软件使用同一个数据目录。"""
    from profit_accounting_26.ui.quick_calculator_app import build_quick_window

    app, window = build_quick_window(data_dir=temp_context.paths.data_dir)
    assert window is not None
    assert window.context.paths.data_dir == temp_context.paths.data_dir
    assert window.context.paths.settings_path == temp_context.paths.settings_path
    assert window.context.paths.database_path == temp_context.paths.database_path
    window.close()
    window.deleteLater()


def test_quick_icon_is_blue_u_and_main_black_unchanged(qapp, temp_context):
    """第18项：Quick runtime 图标为蓝色 U（复用 uu_logo_blue.png），主软件黑色未变。"""
    assert QUICK_ICON_RELATIVE.endswith("uu_logo_blue.png")
    assert Path(resource_path(QUICK_ICON_RELATIVE)).is_file()
    # 未来打包用的同源多尺寸 .ico 已就绪
    assert Path(resource_path("src/profit_accounting_26/ui/assets/uu_quick_blue.ico")).is_file()
    window = QuickCalculatorWindow(temp_context)
    try:
        assert not window.windowIcon().isNull()
    finally:
        window.close()
        window.deleteLater()
    # 主软件黑色 U 图标未被修改（源码仍引用 app_icon_desktop_taskbar.svg）
    main_src = Path(main_app_module.__file__).read_text(encoding="utf-8")
    assert "app_icon_desktop_taskbar.svg" in main_src


def test_pyproject_has_uu_calculator_entry():
    """pyproject 提供 uu-calculator 开发入口（为未来 Setup.exe 保留）。"""
    text = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'uu-calculator = "profit_accounting_26.ui.quick_calculator_app:main"' in text


# ==================================================================
# C 共享核心（任务书 20-22）：无第二套业务计算系统
# ==================================================================


def test_quick_profit_results_driven_by_shared_engine(page):
    """C-21：Quick 的利润区就是共享 CalculationBinder 实例，导出同一套双场景结构。"""
    from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder

    assert isinstance(page.profit_binder, CalculationBinder)
    _install_forwarders(page.context, 1)
    _set_spec(page)
    scenarios = page.profit_binder.export_profit_scenarios()
    assert scenarios.get("schema_version") == "2.6.1-dual-profit-v1"
    assert "no_activity" in scenarios and "activity" in scenarios
    assert scenarios["no_activity"].get("sale_price_usd", 0) > 0
    assert scenarios["activity"].get("profit_rate_on_cost") is not None


def test_quick_has_no_second_business_formula_implementation():
    """C-22：Quick 源码不存在独立物流/利润公式实现（只调用共享入口）。"""
    source = Path(__file__).resolve().parents[2] / "src" / "profit_accounting_26" / "ui" / "quick_calculator_window.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in (
        "volume_divisor",
        "chargeable_weight_kg",
        "volume_weight_kg",
        "calculate_dual_profit",
        "sale_price_for",
        "calculate_profit",
    ):
        assert forbidden not in text, f"Quick 不得出现第二套业务公式: {forbidden}"


# ==================================================================
# P0 回归：任何业务交互永远不得改变顶层窗口尺寸
# （真实缺陷：状态标签 setFixedWidth(sizeHint+4) 追踪漂移 +
#   setWindowFlag 重建原生窗口丢失 fixed 约束 → 窗口横向持续放大）
# ==================================================================


def _pump(app) -> None:
    """完整跑一轮事件循环，确保 LayoutRequest/延迟刷新全部落地。"""
    for _ in range(3):
        app.processEvents()


def test_window_size_contract_is_hard_constant():
    """硬契约：顶层固定尺寸是常量声明，不是从内容 sizeHint 推导。"""
    from profit_accounting_26.ui import quick_calculator_window as mod

    assert mod.QUICK_WINDOW_WIDTH == 448
    assert mod.QUICK_WINDOW_HEIGHT == 475
    # 禁止动态 refit 链复活：源码不得再出现以下模式
    text = Path(mod.__file__).read_text(encoding="utf-8")
    assert "_refit_window" not in text
    assert "setFixedWidth(label.sizeHint()" not in text
    assert "self.adjustSize()" not in text
    assert "setFixedSize(self.size())" not in text


def test_interactions_never_resize_top_level_window(qapp, temp_context):
    """P0 回归：show + 事件循环下，全部交互路径后顶层尺寸/min/max 恒等于初始值。"""
    from PySide6.QtCore import QEvent, QPoint, QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest

    _install_forwarders(temp_context, 2)
    window = QuickCalculatorWindow(temp_context)
    try:
        window.show()
        _pump(qapp)
        initial = (window.width(), window.height())
        assert initial == (448, 475)

        def assert_locked(tag: str) -> None:
            _pump(qapp)
            assert (window.width(), window.height()) == initial, tag
            assert (
                window.minimumWidth(), window.minimumHeight(),
            ) == initial, f"{tag}: minimumSize 被改变"
            assert (
                window.maximumWidth(), window.maximumHeight(),
            ) == initial, f"{tag}: maximumSize 被改变"
            assert window.minimumSize() == window.maximumSize(), tag

        def wheel(spin, times: int = 5) -> None:
            pos = QPoint(spin.width() // 2, spin.height() // 2)
            for _ in range(times):
                ev = QWheelEvent(
                    QPointF(pos), spin.mapToGlobal(pos), QPoint(0, 0), QPoint(0, 120),
                    Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                    Qt.ScrollPhase.NoScrollPhase, False,
                )
                qapp.sendEvent(spin, ev)

        # 1. setValue 小值/大值
        window.spin_length.setValue(2)
        assert_locked("spin.setValue(2)")
        window.spin_length.setValue(160)
        assert_locked("spin.setValue(160)")

        # 2. 键盘输入（lineEdit 真实按键）
        window.spin_length.setFocus()
        window.spin_length.lineEdit().selectAll()
        QTest.keyClicks(window.spin_length.lineEdit(), "160")
        QTest.keyClick(window.spin_length.lineEdit(), Qt.Key.Key_Return)
        assert_locked("keyboard input")

        # 3. 鼠标滚轮（含连续快速滚轮）
        wheel(window.spin_length)
        assert_locked("wheel on length")
        wheel(window.spin_weight, times=30)
        assert_locked("wheel 30x on weight")

        # 4. 货代按钮来回切换
        for button in window._forwarder_buttons:
            if button.isVisible() and button.property("forwarderId"):
                button.click()
        assert_locked("forwarder buttons")

        # 5/6. 尾程 USD / 国内成本 valueChanged
        window.tail_fee_usd.setValue(6.66)
        assert_locked("tail usd valueChanged")
        window.spin_domestic_cost.setValue(88.8)
        assert_locked("domestic cost valueChanged")

        # 7. 完整输入 → 利润重算
        _set_spec(window)
        assert_locked("full recalc")

        # 8. 规则状态 未触发→已触发（真实规则评估路径）
        settings = temp_context.settings_service.load()
        rule = _income_rule("R-P0", "低价补贴", 50.0, 10.0)
        settings["profit_rules"] = [asdict(rule)]
        settings["selected_profit_rule_id"] = rule.id
        temp_context.settings_service.save(settings)
        window._refresh_settings_from_disk()
        window.profit_binder.txt_na_price_usd.setValue(30.0)
        window._apply_compact_rule_status()
        assert_locked("status 未触发→已触发")

        # 9. WindowActivate / settings reload
        qapp.sendEvent(window, QEvent(QEvent.Type.WindowActivate))
        assert_locked("WindowActivate")

        # 10. 置顶开关往返（setWindowFlag 重建原生窗口，P0 真实触发源）
        window.chk_stay_on_top.setChecked(False)
        assert_locked("stay-on-top off")
        window.chk_stay_on_top.setChecked(True)
        assert_locked("stay-on-top on")

        # 11. 清空 → 重新输入
        window.btn_clear.click()
        assert_locked("clear")
        _set_spec(window)
        assert_locked("re-enter after clear")
    finally:
        window.close()
        window.deleteLater()


def test_status_labels_fixed_once_never_drift(qapp, temp_context):
    """状态标签固定尺寸一次设定：多轮重算后宽度不漂移（删除 sizeHint 追踪）。"""
    _install_forwarders(temp_context, 1)
    window = QuickCalculatorWindow(temp_context)
    try:
        window.show()
        _pump(qapp)
        labels = (window.profit_binder.lbl_na_status, window.profit_binder.lbl_act_status)
        widths = [label.width() for label in labels]
        for value in (10.0, 50.0, 120.0, 999.9):
            window.spin_length.setValue(value)
            window.spin_weight.setValue(value * 10)
            _pump(qapp)
        assert [label.width() for label in labels] == widths
        for label in labels:
            assert label.minimumWidth() == label.maximumWidth() == widths[0]
    finally:
        window.close()
        window.deleteLater()
