"""裸尺寸/裸重来源标签位置 UI 契约测试（独立小修正）。

本轮原则：控件不换，只换布局位置——来源标签从输入行最右侧移到各自标题右侧。

覆盖：
A. 两个来源 QLabel 仍存在；
B. objectName 不变（lblBareDimensionSource / lblBareWeightSource）；
C. 来源标签 Y 中心 ≈ 对应标题 Y 中心（同一水平行、垂直居中）；
D. 来源标签位于对应标题右侧；
E. 来源标签不再位于输入框行最右侧；
F. 原有来源文本更新测试（tests/test_pr14_final_contract.py）继续通过。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QDoubleSpinBox, QLabel

from profit_accounting_26.application import AppContext
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


def _find(page, cls, name):
    widget = page._root.findChild(cls, name)
    assert widget is not None, f"缺少控件 {name}"
    return widget


def _center_y(widget) -> float:
    return widget.y() + widget.height() / 2.0


class TestBareSourceLabelPosition:
    def test_source_labels_exist_with_unchanged_object_names(self, shown_page):
        """A/B：两个来源 QLabel 存在且 objectName 不变。"""
        dim = _find(shown_page, QLabel, "lblBareDimensionSource")
        weight = _find(shown_page, QLabel, "lblBareWeightSource")
        assert dim.objectName() == "lblBareDimensionSource"
        assert weight.objectName() == "lblBareWeightSource"

    def test_dimension_source_same_row_right_of_title(self, shown_page):
        """C/D：裸尺寸来源标签与标题同一水平行、垂直居中、位于标题右侧。"""
        title = _find(shown_page, QLabel, "lblBareDimensionsTitle")
        source = _find(shown_page, QLabel, "lblBareDimensionSource")
        assert abs(_center_y(title) - _center_y(source)) <= 2, "裸尺寸来源标签未与标题垂直居中"
        assert source.x() >= title.x() + title.width(), "裸尺寸来源标签未位于标题右侧"
        gap = source.x() - (title.x() + title.width())
        assert 3 <= gap <= 12, f"裸尺寸标题到来源间距异常: {gap}"

    def test_weight_source_same_row_right_of_title(self, shown_page):
        """C/D：裸重来源标签与标题同一水平行、垂直居中、位于标题右侧。"""
        title = _find(shown_page, QLabel, "lblBareWeight")
        source = _find(shown_page, QLabel, "lblBareWeightSource")
        assert abs(_center_y(title) - _center_y(source)) <= 2, "裸重来源标签未与标题垂直居中"
        assert source.x() >= title.x() + title.width(), "裸重来源标签未位于标题右侧"
        gap = source.x() - (title.x() + title.width())
        assert 3 <= gap <= 12, f"裸重标题到来源间距异常: {gap}"

    def test_dimension_source_not_on_input_row(self, shown_page):
        """E：裸尺寸来源标签不再位于输入框行最右侧，而是移到标题行。"""
        source = _find(shown_page, QLabel, "lblBareDimensionSource")
        height_spin = _find(shown_page, QDoubleSpinBox, "spinBareHeightCm")
        assert source.y() + source.height() <= height_spin.y(), "裸尺寸来源标签仍在输入框行"

    def test_weight_source_not_at_far_right(self, shown_page):
        """E：裸重来源标签位于标题与输入框之间，不再被推到行最右侧。"""
        source = _find(shown_page, QLabel, "lblBareWeightSource")
        title = _find(shown_page, QLabel, "lblBareWeight")
        spin = _find(shown_page, QDoubleSpinBox, "spinBareWeightG")
        assert source.x() + source.width() <= spin.x(), "裸重来源标签未位于输入框左侧"
        assert title.x() + title.width() <= source.x(), "裸重来源标签未位于标题右侧"
        # 输入框右侧仍有 g 单位与 stretch 弹性空间（来源标签不再占据最右端）
        unit = _find(shown_page, QLabel, "unit_spinBareWeightG")
        assert unit.x() > spin.x() + spin.width()

    def test_source_texts_still_update(self, shown_page):
        """来源标签文本仍可更新为 未识别 / 图片识别 / AI估算 / 用户确认。"""
        for label in (
            _find(shown_page, QLabel, "lblBareDimensionSource"),
            _find(shown_page, QLabel, "lblBareWeightSource"),
        ):
            for text in ("未识别", "图片识别", "AI估算", "用户确认"):
                label.setText(text)
                assert label.text() == text, f"来源标签文本更新失败: {text}"
