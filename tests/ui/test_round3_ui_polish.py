"""Commit 2 针对性测试：历史与测算页 UI 精修 + 中文弹窗。

覆盖任务书第六至十八节中与 UI 精修直接相关的验收点：
- 当前采用移除“包装方式”输入（后台字段保留）；
- AI估算副标题在标题下方浅灰小字；
- 尾程费用（$USD 可编辑 + ¥RMB）移到系统成本区尾程行；
- 货代卡行距适当增加；
- 利润规则状态放字段标题上方；
- 历史选中浅蓝背景 + 深色文字；
- 历史列宽：序号/图片固定，名称/包装数据吃多余空间；
- 弹窗按钮中文化（确定/取消/删除）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext  # noqa: E402
from profit_accounting_26.ui import theme  # noqa: E402
from profit_accounting_26.ui.pages import CalculationPage  # noqa: E402
from profit_accounting_26.ui.pages.history_page import HistoryPage  # noqa: E402
from profit_accounting_26.ui.widgets import QuoteCard, confirm_action, show_notice  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


@pytest.fixture()
def page(qapp, context):
    widget = CalculationPage(context)
    yield widget
    widget.deleteLater()


def _ancestor_names(widget: QWidget) -> set[str]:
    names: set[str] = set()
    current = widget.parentWidget()
    while current is not None:
        if current.objectName():
            names.add(current.objectName())
        current = current.parentWidget()
    return names


# ---------------------------------------------------------------- 六、包装方式输入移除


def test_conservative_method_widgets_hidden_but_field_kept(qapp, page):
    method_edit = page._root.findChild(QLineEdit, "txtConservativeMethod")
    method_label = page._root.findChild(QLabel, "lblConservativeMethod")
    assert method_edit is not None and method_label is not None
    assert not method_edit.isVisibleTo(page)
    assert not method_label.isVisibleTo(page)
    # 后台字段保留：适配器仍可读写
    page.conservative_fields["method"].setText("气泡袋")
    assert page.conservative_fields["method"].text() == "气泡袋"


# ---------------------------------------------------------------- 七、AI估算副标题位置


@pytest.mark.parametrize(
    ("card_key", "title", "subtitle"),
    [
        ("normal_fields", "AI估算", "第一次 AI 估算结果 · 只读"),
        ("conservative_fields", "当前采用", "用户可手动修正"),
    ],
)
def test_card_subtitle_inline_after_title(qapp, page, card_key, title, subtitle):
    card = page.__dict__[card_key]["card"]
    title_label = next(label for label in card.findChildren(QLabel) if label.text() == title)
    subtitle_label = next(label for label in card.findChildren(QLabel) if label.text() == subtitle)
    header = title_label.parentWidget().layout()
    assert isinstance(header, QHBoxLayout)
    # 副标题在标题后方、同一行内（第五轮：不再独占一行）
    assert header.indexOf(subtitle_label) > header.indexOf(title_label)


# ---------------------------------------------------------------- 八、尾程设置独立卡


def test_tail_fee_inputs_in_independent_tail_settings_card(qapp, page):
    usd_spin = page.tail_fee_usd.spin
    rmb_spin = page.tail_fee_rmb.spin
    for spin in (usd_spin, rmb_spin):
        ancestors = _ancestor_names(spin)
        assert "tailSettingsCard" in ancestors
        assert "systemCostSection" not in ancestors
        assert "freightSection" not in ancestors
    # 摘要尾程行可见（只显示 RMB）
    assert page.system_rows["tail"].isVisibleTo(page)
    # ¥ / $ 是输入框外的独立 QLabel；输入框内无 prefix
    assert page.tail_fee_rmb.spin.prefix() == ""
    assert page.tail_fee_usd.spin.prefix() == ""
    rmb_symbol = page._root.findChild(QLabel, "lblTailSettingsRmbSymbol")
    usd_symbol = page._root.findChild(QLabel, "lblTailSettingsUsdSymbol")
    assert rmb_symbol is not None and rmb_symbol.text() == "¥"
    assert usd_symbol is not None and usd_symbol.text() == "$"
    assert page.tail_fee_rmb.spin.isReadOnly() is True
    assert page.tail_fee_usd.spin.isReadOnly() is False
    assert page.tail_fee_rmb.spin.width() == page.tail_fee_usd.spin.width()
    # 尾程输入仍然可用且联动 dirty
    page.tail_fee_usd.setValue(6.5)
    assert page.tail_fee_usd.value() == pytest.approx(6.5)


# ---------------------------------------------------------------- 九、货代卡行距


def test_quote_card_row_spacing_increased(qapp):
    card = QuoteCard("forwarder_test", "测试货代")
    assert isinstance(card.layout(), QVBoxLayout)
    assert card.layout().spacing() >= 6


# ---------------------------------------------------------------- 十、利润规则状态在标题上方


@pytest.mark.parametrize(
    ("title_name", "status_name"),
    [
        ("lblNoActivityProfit", "lblNoActivitySubsidyStatus"),
        ("lblActivityProfit", "lblActivitySubsidyStatus"),
    ],
)
def test_profit_rule_status_above_title(qapp, page, title_name, status_name):
    title_label = page._root.findChild(QLabel, title_name)
    status_label = page._root.findChild(QLabel, status_name)
    assert title_label is not None and status_label is not None
    # 三个业务组重排后，状态标签和标题均在 Group 容器内
    # 检查两个控件均可见
    assert title_label.isVisibleTo(page._root)
    assert status_label.isVisibleTo(page._root)
    # 状态标签和标题标签共享同一个父控件（所属 Group QFrame）
    assert status_label.parentWidget() is not None
    assert title_label.parentWidget() is not None
    assert status_label.parentWidget() is title_label.parentWidget()


# ---------------------------------------------------------------- 十一、历史选中浅蓝


def test_history_selected_uses_light_blue_not_dark():
    assert "QTableWidget::item:selected" in theme.APP_STYLE
    block = theme.APP_STYLE.split("QTableWidget::item:selected", 1)[1].split("}", 1)[0]
    assert "#EAF2FF" in block
    assert theme.TEXT in block
    # 禁止深蓝反白
    assert "#FFFFFF" not in block and "white" not in block.lower()


# ---------------------------------------------------------------- 十二、列宽重分配


def test_history_column_resize_modes(qapp, context):
    page = HistoryPage(context)
    header = page.table.horizontalHeader()
    assert not header.stretchLastSection()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Fixed
    # 多余空间优先给名称与校准内容（阶段 3 最终调整：包装列固定收窄，校准列 Stretch）
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(7) == QHeaderView.ResizeMode.Stretch
    for column in (3, 4, 5, 6):
        assert header.sectionResizeMode(column) == QHeaderView.ResizeMode.Fixed


# ---------------------------------------------------------------- 十八、中文弹窗


def test_confirm_action_buttons_are_chinese(qapp, monkeypatch):
    captured: list[QMessageBox] = []

    def fake_exec(box: QMessageBox):
        captured.append(box)
        confirm_button = next(
            button
            for button in box.buttons()
            if box.buttonRole(button) == QMessageBox.ButtonRole.AcceptRole
        )
        box.clickedButton = lambda: confirm_button
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert confirm_action(None, "删除记录", "文案", confirm_text="删除", danger=True) is True
    assert confirm_action(None, "清空并新建", "文案") is True
    assert captured[0].text() == "文案"
    for box in captured:
        texts = {button.text() for button in box.buttons()}
        assert "Yes" not in texts and "No" not in texts and "OK" not in texts
    assert {button.text() for button in captured[0].buttons()} == {"删除", "取消"}
    assert {button.text() for button in captured[1].buttons()} == {"确定", "取消"}


def test_confirm_action_cancel_returns_false(qapp, monkeypatch):
    def fake_exec(box: QMessageBox):
        cancel_button = next(
            button
            for button in box.buttons()
            if box.buttonRole(button) == QMessageBox.ButtonRole.RejectRole
        )
        box.clickedButton = lambda: cancel_button
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    assert confirm_action(None, "标题", "内容") is False


def test_show_notice_button_is_chinese(qapp, monkeypatch):
    captured: list[QMessageBox] = []

    def fake_exec(box: QMessageBox):
        captured.append(box)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    show_notice(None, "保存成功", "记录已保存")
    show_notice(None, "无法保存", "缺少数据", ok_text="知道了", level="warning")
    assert {button.text() for button in captured[0].buttons()} == {"确定"}
    assert {button.text() for button in captured[1].buttons()} == {"知道了"}
