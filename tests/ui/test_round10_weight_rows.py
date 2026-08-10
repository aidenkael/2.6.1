"""第十轮：裸重 / AI包装后重量 / 当前采用包装后重量 三行统一紧凑结构（标题→输入框→紧贴g→stretch）。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QLabel

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.pages import CalculationPage


@pytest.fixture()
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture()
def shown_page(qapp, temp_context):
    page = CalculationPage(temp_context)
    settings = page.context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    page.context.settings_service.save(settings)
    page.show()
    page.resize(1840, 1020)
    qapp.processEvents()
    yield page
    page.close()
    page.deleteLater()
    qapp.processEvents()


def _find(page, cls, name):
    widget = page._root.findChild(cls, name)
    assert widget is not None, f"缺少控件 {name}"
    return widget


class TestThreeWeightRowsUnified:
    def _spins(self, page):
        return (
            _find(page, QDoubleSpinBox, "spinBareWeightG"),
            _find(page, QDoubleSpinBox, "spinNormalWeightG"),
            _find(page, QDoubleSpinBox, "spinConservativeWeightG"),
        )

    def test_three_spins_same_width_around_96(self, shown_page, qapp):
        spins = self._spins(shown_page)
        widths = {spin.width() for spin in spins}
        assert len(widths) == 1, f"三个重量输入框宽度不一致: {widths}"
        width = widths.pop()
        assert 92 <= width <= 100, f"重量输入框宽度异常: {width}"

    def test_ai_and_conservative_weight_rows_symmetric(self, shown_page, qapp):
        left = _find(shown_page, QDoubleSpinBox, "spinNormalWeightG")
        right = _find(shown_page, QDoubleSpinBox, "spinConservativeWeightG")
        assert abs(left.geometry().left() - right.geometry().left()) <= 4
        assert abs(left.geometry().width() - right.geometry().width()) <= 2

    def test_g_label_tight_after_spin_on_all_three(self, shown_page, qapp):
        pairs = (
            ("spinBareWeightG", "unit_spinBareWeightG"),
            ("spinNormalWeightG", "unit_spinNormalWeightG"),
            ("spinConservativeWeightG", "unit_spinConservativeWeightG"),
        )
        for spin_name, unit_name in pairs:
            spin = _find(shown_page, QDoubleSpinBox, spin_name)
            unit = _find(shown_page, QLabel, unit_name)
            gap = unit.geometry().left() - spin.geometry().right()
            assert 3 <= gap <= 8, f"{spin_name} 到 g 间距异常: {gap}"

    def test_g_not_pushed_to_far_right(self, shown_page, qapp):
        # g 右侧仍有弹性空间（stretch），而不是被推到卡片最右端
        for unit_name, card_name in (
            ("unit_spinBareWeightG", "bareProductCard"),
            ("unit_spinNormalWeightG", "normalPackageCard"),
            ("unit_spinConservativeWeightG", "conservativePackageCard"),
        ):
            unit = _find(shown_page, QLabel, unit_name)
            card = shown_page._root.findChild(QFrame, card_name)
            assert card is not None, f"缺少卡片 {card_name}"
            assert card.geometry().right() - unit.geometry().right() >= 8, f"{card_name} 内 g 被推到最右"

    def test_title_to_spin_gap_is_small(self, shown_page, qapp):
        # AI估算/当前采用 两行结构不变：标题 → 输入框，间距 6-18px
        pairs = (
            ("lblNormalWeight", "spinNormalWeightG"),
            ("lblConservativeWeight", "spinConservativeWeightG"),
        )
        for label_name, spin_name in pairs:
            label = _find(shown_page, QLabel, label_name)
            spin = _find(shown_page, QDoubleSpinBox, spin_name)
            gap = spin.geometry().left() - label.geometry().right()
            assert 6 <= gap <= 18, f"{label_name} 到输入框间距异常: {gap}"
        # 裸重行：标题 → 来源标签 → 输入框，两侧间距均小而自然
        title = _find(shown_page, QLabel, "lblBareWeight")
        source = _find(shown_page, QLabel, "lblBareWeightSource")
        spin = _find(shown_page, QDoubleSpinBox, "spinBareWeightG")
        title_to_source = source.geometry().left() - title.geometry().right()
        source_to_spin = spin.geometry().left() - source.geometry().right()
        assert 3 <= title_to_source <= 12, f"裸重标题到来源间距异常: {title_to_source}"
        assert 3 <= source_to_spin <= 12, f"裸重来源到输入框间距异常: {source_to_spin}"

    def test_9999_9_fits_inside_spin(self, shown_page, qapp):
        for spin_name in ("spinBareWeightG", "spinNormalWeightG", "spinConservativeWeightG"):
            spin = _find(shown_page, QDoubleSpinBox, spin_name)
            spin.setValue(9999.9)
            qapp.processEvents()
            text_width = spin.fontMetrics().horizontalAdvance("9999.9")
            assert text_width + 16 <= spin.width(), f"{spin_name} 无法完整显示 9999.9"

    def test_other_dimension_spins_unchanged(self, shown_page, qapp):
        # 尺寸输入框不受本轮影响：左右卡长度框仍存在且等宽
        left_length = _find(shown_page, QDoubleSpinBox, "spinNormalLengthCm")
        right_length = _find(shown_page, QDoubleSpinBox, "spinConservativeLengthCm")
        assert left_length.width() == right_length.width()
        assert left_length.width() > 40
