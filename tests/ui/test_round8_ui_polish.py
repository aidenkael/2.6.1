"""第八轮 UI 收口：用户修正示例文字层 + 重量输入框/g 间距的真实渲染验证。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QTextEdit

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


class TestUserCorrectionExampleLayer:
    def test_example_visible_when_empty_with_full_two_lines(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        assert isinstance(edit, QTextEdit)
        assert edit.toPlainText() == ""
        assert edit.example.isVisibleTo(edit.viewport())
        assert edit.example.text().count("\n") == 1
        assert "深圳货代纯头程26元" in edit.example.text()
        assert "义乌货代纯头程10元" in edit.example.text()

    def test_example_hidden_on_input_and_back_on_clear(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        edit.setPlainText("实际备注内容")
        qapp.processEvents()
        assert not edit.example.isVisible()
        assert edit.toPlainText() == "实际备注内容"
        edit.clear()
        qapp.processEvents()
        assert edit.example.isVisibleTo(edit.viewport())
        assert edit.toPlainText() == ""

    def test_example_geometry_fits_viewport_and_no_dirty(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        example = edit.example
        viewport = edit.viewport()
        assert example.width() <= viewport.width()
        assert example.geometry().left() >= 8
        assert example.geometry().right() <= viewport.width() - 8
        needed = example.heightForWidth(example.width())
        assert needed <= example.height(), "示例完整文本高度超过可显示区域"
        # 示例显示变化不污染 user_note / 不触发校准 dirty
        shown_page.recalculate()
        assert shown_page.user_correction.text() == ""
        assert shown_page.user_calibration_dirty is False

    def test_example_not_focusable_or_clickable(self, shown_page, qapp):
        edit = shown_page.user_correction._widget
        assert edit.example.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert edit.example.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert edit.example.parent() is edit.viewport()


class TestWeightRowGap:
    def test_weight_spins_same_fixed_width_not_expanding(self, shown_page, qapp):
        left = shown_page.normal_fields["weight"].spin
        right = shown_page.conservative_fields["weight"].spin
        assert left.width() == right.width()
        assert 92 <= left.width() <= 100
        assert left.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Expanding
        assert right.sizePolicy().horizontalPolicy() != QSizePolicy.Policy.Expanding

    def test_g_label_tight_to_spin_on_both_cards(self, shown_page, qapp):
        left_spin = shown_page.normal_fields["weight"].spin
        right_spin = shown_page.conservative_fields["weight"].spin
        left_unit = shown_page._root.findChild(QLabel, "unit_spinNormalWeightG")
        right_unit = shown_page._root.findChild(QLabel, "unit_spinConservativeWeightG")
        assert left_unit is not None and right_unit is not None
        assert left_unit.text() == "g" and right_unit.text() == "g"
        for spin, unit in ((left_spin, left_unit), (right_spin, right_unit)):
            gap = unit.geometry().left() - spin.geometry().right()
            assert 2 <= gap <= 12, f"g 与输入框间距异常: {gap}"
        # 两侧 g 的 X 位置基本对应（镜像）
        assert abs(left_unit.geometry().left() - right_unit.geometry().left()) <= 4
        # g 不再被推到卡片最右侧：g 右侧仍有弹性空间
        card = shown_page.normal_fields["card"]
        assert card.geometry().right() - left_unit.geometry().right() >= 8
