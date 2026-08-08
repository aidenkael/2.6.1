"""第四轮 UI 精修：系统总成本六行排版、0 值红色提醒、设置表格与中文弹窗、历史顶部对齐。

覆盖任务书第十九节 E 组与第四/五/十三/十四/十五节：
- 系统总成本固定 6 行：采购成本 / 国内运费 / 头程(带货代名) / 服务费 / 尾程(USD/RMB) / 总成本；
- 0 值只做红色弱提醒，不阻止计算；
- 历史页 8 列不变、文字列顶部对齐、图片/序号保持居中；
- 货代启用/操作列居中、按钮文字不裁切；
- 删除/归档确认弹窗统一使用中文按钮（confirm_action）。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpacerItem,
    QVBoxLayout,
)

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.pages import CalculationPage, HistoryPage, SettingsPage


@pytest.fixture
def temp_context(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _install_forwarders(context):
    settings = context.settings_service.load()
    shenzhen = SettingsService.new_forwarder("深圳货代", 80.0, 10.0, 8000.0)
    yiwu = SettingsService.new_forwarder("义乌货代", 100.0, 6.0, 8000.0)
    settings["forwarders"] = [asdict(shenzhen), asdict(yiwu)]
    settings["selected_forwarder_id"] = shenzhen.id
    context.settings_service.save(settings)
    return shenzhen.id, yiwu.id


def _arm_page(page):
    page.product_cost.setValue(66.80)
    page.domestic_shipping.setValue(28.0)
    page.conservative_fields["length"].setValue(25.0)
    page.conservative_fields["width"].setValue(18.0)
    page.conservative_fields["height"].setValue(6.0)
    page.conservative_fields["weight"].setValue(320.0)
    _install_forwarders(page.context)
    page.refresh_settings()
    page.recalculate()


# ---------------------------------------------------------------------------
# 五：系统总成本固定 6 行
# ---------------------------------------------------------------------------


class TestSystemCostSixRows:
    def test_row_labels_fixed_six_rows(self, qapp, temp_context):
        """六行标签固定：采购成本 / 国内运费 / 头程 / 服务费 / 尾程 + 总成本。"""
        page = CalculationPage(temp_context)
        try:
            root = page._root
            assert root.findChild(QLabel, "lblSystemCostName0").text() == "采购成本"
            assert root.findChild(QLabel, "lblSystemCostName1").text() == "国内运费"
            assert root.findChild(QLabel, "lblSystemCostName2").text() == "头程"
            assert root.findChild(QLabel, "lblSystemCostName3").text() == "服务费"
            assert root.findChild(QLabel, "lblSystemCostName6").text() == "尾程"
            total_name = root.findChild(QLabel, "lblSystemTotalName")
            assert total_name is not None and total_name.text() == "总成本"
            # 旧的重量/计费重/物流总价行保持隐藏
            for hidden in ("lblSystemCostName4", "lblSystemCostValue4", "lblSystemCostName5", "lblSystemCostValue5"):
                assert not root.findChild(QLabel, hidden).isVisibleTo(page._root), f"{hidden} 应隐藏"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_rows_filled_from_single_calculation_result(self, qapp, temp_context):
        """计算后六行只读正式 Calculation 结果：头程带货代名、尾程 USD/RMB、总成本左对齐不加前缀。"""
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            quote = page.current_quote
            assert quote is not None
            assert page.system_rows["product"].text() == "¥66.80"
            assert page.system_rows["domestic"].text() == "¥28.00"
            assert "深圳货代" in page.system_rows["first_mile"].text()
            assert f"¥{quote.weight_fee_rmb:.2f}" in page.system_rows["first_mile"].text()
            assert page.system_rows["service"].text() == f"¥{quote.fixed_fee_rmb:.2f}"
            assert "$" in page.system_rows["tail"].text() and "¥" in page.system_rows["tail"].text()
            # 总成本：左对齐金额，不带“总成本”前缀，不加粗由 totalBold 属性承载
            assert page.system_total.text() == f"¥{page.current_system_cost:.2f}"
            assert not page.system_total.text().startswith("总成本")
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_zero_cost_shows_red_hint_without_blocking(self, qapp, temp_context):
        """第 10 项：采购/国内运费为 0 时金额仍显示且带 zeroWarn 红色弱提醒。"""
        page = CalculationPage(temp_context)
        try:
            page.product_cost.setValue(0.0)
            page.domestic_shipping.setValue(0.0)
            page.conservative_fields["length"].setValue(25.0)
            page.conservative_fields["width"].setValue(18.0)
            page.conservative_fields["height"].setValue(6.0)
            page.conservative_fields["weight"].setValue(320.0)
            _install_forwarders(page.context)
            page.refresh_settings()
            page.recalculate()
            assert page.current_quote is not None
            assert page.system_rows["product"].text() == "¥0.00"
            assert page.system_rows["domestic"].text() == "¥0.00"
            assert page.system_rows["product"].property("zeroWarn") is True
            assert page.system_rows["domestic"].property("zeroWarn") is True
            # 非 0 行与总成本不带弱提醒
            assert not page.system_rows["service"].property("zeroWarn")
            # 恢复正常金额后提醒消除
            page.product_cost.setValue(10.0)
            page.recalculate()
            assert not page.system_rows["product"].property("zeroWarn")
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 十五/十六：历史记录文字列顶部对齐
# ---------------------------------------------------------------------------


def _create_record(context) -> str:
    payload = {
        "product_name": "顶部对齐测试商品",
        "product_link": "",
        "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T01:00:00Z",
        "product_cost_rmb": 66.80,
        "domestic_shipping_rmb": 28.00,
        "shein_quote_usd": 30.0,
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "conservative": {
                    "packaging_method": "气泡袋",
                    "length_cm": 17,
                    "width_cm": 32,
                    "height_cm": 17,
                    "weight_g": 720,
                },
            },
            "calculated": {
                "system_cost_rmb": 237.26,
                "exchange_rate": 7.2,
                "forwarder_name": "深圳货代",
                "logistics_quote": {
                    "weight_fee_rmb": 92.48,
                    "fixed_fee_rmb": 10.0,
                    "tail_fee_rmb": 39.98,
                    "total_logistics_rmb": 142.46,
                },
            },
        },
        "profit_scenarios": {
            "no_activity": {"sale_price_usd": 30.0, "profit_rmb": 78.9},
        },
    }
    return context.record_service.save(payload, images=[], ai_initial=None)


class TestHistoryTopAlignment:
    def test_table_still_has_eight_columns(self, qapp, temp_context):
        """第 23 项：历史页仍然只有 8 列。"""
        _create_record(temp_context)
        page = HistoryPage(temp_context)
        try:
            assert page.table.columnCount() == 8
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_text_columns_are_top_aligned(self, qapp, temp_context):
        """第 24 项：名称/成本/售价/利润/包装/校准列第一行从统一顶部基线开始。"""
        _create_record(temp_context)
        page = HistoryPage(temp_context)
        try:
            row = 0
            for col in (2, 3, 4, 5, 6, 7):
                container = page.table.cellWidget(row, col)
                layout = container.layout()
                assert isinstance(layout, QVBoxLayout), f"列 {col} 应为垂直容器"
                first = layout.itemAt(0)
                assert first is not None and first.widget() is not None, f"列 {col} 第一个控件缺失"
                # 末尾 stretch 把内容压到顶部：这是顶部对齐的结构保证
                last = layout.itemAt(layout.count() - 1)
                assert isinstance(last, QSpacerItem) or last.spacerItem() is not None, (
                    f"列 {col} 缺少顶部对齐 stretch"
                )
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_image_and_index_stay_centered(self, qapp, temp_context):
        """第 25 项：图片列仍垂直居中、序号仍居中。"""
        _create_record(temp_context)
        page = HistoryPage(temp_context)
        try:
            row = 0
            anchor = page.table.item(row, 0)
            assert anchor.textAlignment() & Qt.AlignmentFlag.AlignCenter
            image_cell = page.table.cellWidget(row, 1)
            assert isinstance(image_cell.layout(), QHBoxLayout), "图片列应保持水平居中容器"
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 十三：货代启用/操作列 UI
# ---------------------------------------------------------------------------


class TestForwarderTableUI:
    def test_checkbox_and_buttons_centered_with_min_width(self, qapp, temp_context):
        """第 26 项：启用复选框与操作按钮居中，按钮最小宽度保证文字不裁切。"""
        _install_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            row = 0
            # 启用列：容器内复选框水平+垂直居中
            enabled_container = page.forwarder_table.cellWidget(row, 4)
            enabled_layout = enabled_container.layout()
            assert isinstance(enabled_layout, QHBoxLayout)
            assert enabled_layout.itemAt(0).alignment() & Qt.AlignmentFlag.AlignCenter
            assert enabled_container.findChild(QCheckBox) is not None
            # 归档后操作列按钮：恢复 + 永久删除，均居中且不裁字
            import profit_accounting_26.ui.pages.settings_page as spm

            original_confirm = spm.confirm_action
            spm.confirm_action = lambda *a, **k: True
            try:
                identifier = page.forwarder_table.item(row, 6).text()
                page.toggle_forwarder_archive(identifier)
            finally:
                spm.confirm_action = original_confirm
            op_container = page.forwarder_table.cellWidget(row, 5)
            buttons = op_container.findChildren(QPushButton)
            texts = {btn.text() for btn in buttons}
            assert texts == {"恢复", "永久删除"}
            for btn in buttons:
                text_width = btn.fontMetrics().horizontalAdvance(btn.text())
                assert btn.minimumWidth() >= text_width, f"按钮 {btn.text()} 最小宽度不足会裁字"
            # 行高足够容纳按钮垂直居中
            assert page.forwarder_table.verticalHeader().defaultSectionSize() >= 40
            # 操作列宽度足够两个按钮并排
            assert page.forwarder_table.columnWidth(5) >= 150
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 十四：中文确认弹窗统一
# ---------------------------------------------------------------------------


class TestChineseConfirmDialogs:
    def test_delete_and_archive_use_chinese_confirm_not_yes_no(self, qapp, temp_context, monkeypatch):
        """第 27 项：货代/规则的归档与删除统一走中文 confirm_action，不再出现 Yes/No。"""
        import profit_accounting_26.ui.pages.settings_page as spm

        calls: list[tuple[str, str]] = []

        def _fake_confirm(_parent, title, text, **_kwargs):
            calls.append((title, text))
            return True

        monkeypatch.setattr(spm, "confirm_action", _fake_confirm)
        monkeypatch.setattr(
            spm.QMessageBox, "question",
            staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应再使用 Yes/No 英文弹窗"))),
        )

        _install_forwarders(temp_context)
        page = SettingsPage(temp_context)
        try:
            identifier = page.forwarder_table.item(0, 6).text()
            # 归档 → 永久删除（两步都走中文确认）
            page.toggle_forwarder_archive(identifier)
            page._delete_forwarder_permanently(identifier)
            # 规则归档与删除
            assert page.rules_data
            page.rule_list.setCurrentRow(0)
            page.archive_current_rule()
            archived_visible = page.visible_rule_indices
            if page.rules_data:
                # 若还有未归档规则则测试删除；归档后列表可能为空
                if page.rule_list.count() > 0:
                    page.rule_list.setCurrentRow(0)
                    page.delete_current_rule()
            del archived_visible
            titles = [title for title, _ in calls]
            assert "归档货代" in titles
            assert "永久删除" in titles
            assert "归档规则" in titles
            assert all(any(ch >= "\u4e00" for ch in text) for _title, text in calls), "弹窗文案必须为中文"
        finally:
            page.deleteLater()
            qapp.processEvents()
