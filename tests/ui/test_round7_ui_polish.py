"""第七轮 UI 收口：实际 geometry/layout 验证（尾程设置独立卡、总成本五行连续、头程标签不裁切、placeholder 完整）。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QLabel, QTextEdit

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.pages import CalculationPage


@pytest.fixture()
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture()
def shown_page(qapp, temp_context):
    page = CalculationPage(temp_context)
    page.show()
    page.resize(1840, 1020)
    qapp.processEvents()
    yield page
    page.close()
    page.deleteLater()
    qapp.processEvents()


def _install_forwarders(context):
    settings = context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    context.settings_service.save(settings)


def _arm(shown_page):
    _install_forwarders(shown_page.context)
    shown_page.conservative_fields["length"].setValue(25.0)
    shown_page.conservative_fields["width"].setValue(18.0)
    shown_page.conservative_fields["height"].setValue(6.0)
    shown_page.conservative_fields["weight"].setValue(320.0)
    shown_page.refresh_settings()
    shown_page.recalculate()


def _widget(page, cls, name):
    widget = page._root.findChild(cls, name)
    assert widget is not None, f"缺少控件 {name}"
    return widget


class TestTailSettingsCard:
    def test_tail_card_and_cost_card_are_distinct_with_spacing(self, shown_page, qapp):
        tail = _widget(shown_page, QFrame, "tailSettingsCard")
        cost = _widget(shown_page, QFrame, "systemCostSection")
        assert tail is not cost
        assert tail.isVisibleTo(shown_page._root)
        assert cost.isVisibleTo(shown_page._root)
        gap = cost.geometry().top() - tail.geometry().bottom()
        assert 6 <= gap <= 14, f"两卡间距异常: {gap}"
        assert not tail.geometry().intersects(cost.geometry())

    def test_symbols_outside_inputs_and_no_overlap(self, shown_page, qapp):
        rmb_spin = _widget(shown_page, QDoubleSpinBox, "spinTailFreightRmb")
        usd_spin = _widget(shown_page, QDoubleSpinBox, "spinTailFreightUsd")
        rmb_symbol = _widget(shown_page, QLabel, "lblTailSettingsRmbSymbol")
        usd_symbol = _widget(shown_page, QLabel, "lblTailSettingsUsdSymbol")
        assert rmb_symbol.text() == "¥"
        assert usd_symbol.text() == "$"
        assert rmb_spin.prefix() == "" and rmb_spin.suffix() == ""
        assert usd_spin.prefix() == "" and usd_spin.suffix() == ""
        assert not rmb_symbol.geometry().intersects(rmb_spin.geometry())
        assert not usd_symbol.geometry().intersects(usd_spin.geometry())
        # 符号在输入框左侧
        assert rmb_symbol.geometry().right() <= rmb_spin.geometry().left()
        assert usd_symbol.geometry().right() <= usd_spin.geometry().left()

    def test_inputs_same_width_and_inside_tail_card(self, shown_page, qapp):
        tail = _widget(shown_page, QFrame, "tailSettingsCard")
        rmb_spin = _widget(shown_page, QDoubleSpinBox, "spinTailFreightRmb")
        usd_spin = _widget(shown_page, QDoubleSpinBox, "spinTailFreightUsd")
        assert rmb_spin.width() == usd_spin.width()
        assert 70 <= rmb_spin.width() <= 120
        for spin in (rmb_spin, usd_spin):
            center = spin.mapTo(tail, spin.rect().center())
            assert tail.rect().contains(center)

    def test_title_uses_section_title_style(self, shown_page, qapp):
        title = _widget(shown_page, QLabel, "lblTailSettingsTitle")
        assert title.text() == "尾程设置"
        assert title.property("sectionTitle") is True


class TestSystemCostRows:
    def test_five_rows_equally_spaced_and_order(self, shown_page, qapp):
        _arm(shown_page)
        qapp.processEvents()
        names = {
            "product": _widget(shown_page, QLabel, "lblSystemCostName0"),
            "domestic": _widget(shown_page, QLabel, "lblSystemCostName1"),
            "first_mile": _widget(shown_page, QLabel, "lblSystemCostName2"),
            "service": _widget(shown_page, QLabel, "lblSystemCostName3"),
            "tail": _widget(shown_page, QLabel, "lblSystemCostName6"),
        }
        assert names["product"].text() == "采购成本"
        assert names["domestic"].text() == "国内运费"
        assert names["first_mile"].text() == "头程（深圳）"
        assert names["service"].text() == "服务费"
        assert names["tail"].text() == "尾程"
        ys = [names[key].geometry().top() for key in ("product", "domestic", "first_mile", "service", "tail")]
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        assert max(gaps) - min(gaps) <= 8, f"五行间距不均匀: {gaps}"
        # 服务费与尾程之间不得出现异常大空白
        assert names["tail"].geometry().top() - names["service"].geometry().bottom() <= 12

    def test_first_mile_label_never_clipped_shenzhen_and_yiwu(self, shown_page, qapp):
        _arm(shown_page)
        qapp.processEvents()
        label = _widget(shown_page, QLabel, "lblSystemCostName2")
        assert label.text() == "头程（深圳）"
        assert label.width() >= label.sizeHint().width(), "头程（深圳）被裁切"
        yiwu = next(item for item in shown_page.context.settings_service.load()["forwarders"]
                    if item["name"] == "义乌货代")
        shown_page.selected_forwarder_id = yiwu["id"]
        shown_page.recalculate()
        qapp.processEvents()
        assert label.text() == "头程（义乌）"
        assert label.width() >= label.sizeHint().width(), "头程（义乌）被裁切"

    def test_total_rmb_above_usd_right_aligned(self, shown_page, qapp):
        _arm(shown_page)
        qapp.processEvents()
        rmb = _widget(shown_page, QLabel, "lblSystemTotalRmb")
        usd = _widget(shown_page, QLabel, "lblSystemTotalUsd")
        assert rmb.geometry().top() < usd.geometry().top()
        assert usd.isVisibleTo(shown_page._root)
        assert rmb.alignment() & 0x2  # AlignRight
        assert usd.alignment() & 0x2


class TestUserCorrectionPlaceholderGeometry:
    def test_placeholder_has_real_newline_and_wrap(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        assert isinstance(edit, QTextEdit)
        assert "\n" in edit.placeholderText()
        assert "深圳货代纯头程26元" in edit.placeholderText()
        assert "义乌货代纯头程10元" in edit.placeholderText()
        assert edit.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
        assert edit.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    def test_box_height_supports_wrapped_example(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        line_height = edit.fontMetrics().lineSpacing()
        assert edit.height() >= 4 * line_height, "用户修正框高度不足以完整显示两段示例"
