"""第五轮 UI 精修：AI估算/当前采用镜像、包装方式中文化、动态纯头程提示、尾程/总成本排版、历史分隔线与列宽。"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dataclasses import asdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QHeaderView, QLabel, QTextEdit, QVBoxLayout

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.domain.models import PackagingProposal, PackagingScenario
from profit_accounting_26.ui.pages import CalculationPage, HistoryPage


@pytest.fixture()
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


def _proposal(method: str = "polybag") -> PackagingProposal:
    normal = PackagingScenario(
        label="正常档", packaging_method=method,
        length_cm=47.0, width_cm=32.0, height_cm=17.0, weight_g=720.0,
    )
    conservative = PackagingScenario(
        label="保守档", packaging_method=method,
        length_cm=49.0, width_cm=34.0, height_cm=19.0, weight_g=820.0,
    )
    return PackagingProposal(normal=normal, conservative=conservative)


# ---------------------------------------------------------------------------
# AI 发货判断直接展示外部 shipment.state
# ---------------------------------------------------------------------------


class TestPackagingMethodDirectDisplay:
    def test_ai_card_displays_external_state_without_rewriting(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            page.apply_proposal(_proposal("polybag"))
            assert page.normal_fields["method"].text() == "polybag"
            assert page.conservative_fields["method"].text() == "polybag"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_history_restore_does_not_rewrite_external_state(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            page._fill_package_fields(page.normal_fields, {"packaging_method": "box"})
            assert page.normal_fields["method"].text() == "box"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "bubble mailer"})
            assert page.normal_fields["method"].text() == "bubble mailer"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "vacuum bag"})
            assert page.normal_fields["method"].text() == "vacuum bag"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "bag"})
            assert page.normal_fields["method"].text() == "bag"
            # 未知值也保持原样，不伪造 AI 判断。
            page._fill_package_fields(page.normal_fields, {"packaging_method": "strange_method_xyz"})
            assert page.normal_fields["method"].text() == "strange_method_xyz"
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# AI估算 / 当前采用 两张卡镜像
# ---------------------------------------------------------------------------


class TestMirrorCards:
    def _card_layout(self, page, fields) -> QGridLayout:
        layout = fields["card"].layout()
        assert isinstance(layout, QGridLayout)
        return layout

    def test_both_cards_share_same_row_structure(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            left = self._card_layout(page, page.normal_fields)
            right = self._card_layout(page, page.conservative_fields)
            assert left.rowCount() == right.rowCount()
            # 底部多行框在同一行（row 5），高度一致
            left_bottom = page.normal_fields["method"]._widget
            right_bottom = page.user_correction._widget
            assert isinstance(left_bottom, QTextEdit)
            assert isinstance(right_bottom, QTextEdit)
            assert left_bottom.minimumHeight() == right_bottom.minimumHeight()
            assert left_bottom.maximumHeight() == right_bottom.maximumHeight()
            assert 68 <= left_bottom.minimumHeight() <= 88
            # 底部标签：左“包装方式”，右“用户修正”
            assert page._root.findChild(QLabel, "lblNormalDims").text() == "包装尺寸（默认 cm）"
            assert page._root.findChild(QLabel, "lblConservativeDims").text() == "包装尺寸（默认 cm）"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_subtitle_inline_after_title(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            def _inline_found(card, title: str, subtitle_marker: str) -> bool:
                for box in card.findChildren(QHBoxLayout):
                    widgets = [box.itemAt(i).widget() for i in range(box.count())]
                    texts = [w.text() for w in widgets if isinstance(w, QLabel)]
                    if any(text == title for text in texts) and any(subtitle_marker in text for text in texts):
                        return True
                return False

            assert _inline_found(page.normal_fields["card"], "AI估算", "第一次 AI 估算结果")
            assert _inline_found(page.conservative_fields["card"], "当前采用", "用户可手动修正")
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 用户修正：动态提示已删除，placeholder 为两行静态示例
# ---------------------------------------------------------------------------


class TestUserCorrectionPlaceholder:
    def test_no_dynamic_forwarder_hint_exists(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            assert not hasattr(page, "user_correction_hint")
            card = page.conservative_fields["card"]
            texts = [label.text() for label in card.findChildren(QLabel)]
            # 动态“当前：{货代}，纯头程…”提示已删除；示例文字里的“纯头程”是两行示例内容
            assert not any(text.startswith("当前：") for text in texts)
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_user_correction_placeholder_is_single_line_example(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            edit = page.user_correction._widget
            example = edit.example.text()
            # PR #40：示例文字精简为一行（移除"若商品识别错误"过期说明）
            assert "填写用于重估的修正（本框内容优先）" in example
            assert "若商品识别错误" not in example
            assert "头程" not in example and "货代" not in example
            # 示例是 viewport 子控件且不影响真实内容
            assert edit.example.parent() is edit.viewport()
            assert edit.toPlainText() == ""
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_placeholder_not_written_to_note_or_dirty(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            assert page.user_correction.text() == ""
            assert page.user_calibration_dirty is False
            page.recalculate()
            assert page.user_correction.text() == ""
            assert page.user_calibration_dirty is False
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 尾程输入与系统总成本
# ---------------------------------------------------------------------------


class TestTailFeeAndCostSummary:
    def test_tail_symbols_readonly_and_rate_linked(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            assert page.tail_fee_rmb.spin.isReadOnly() is True
            assert page.tail_fee_usd.spin.isReadOnly() is False
            # 输入框内只有数字：无 prefix/suffix；¥ / $ 是框外独立 QLabel
            assert page.tail_fee_rmb.spin.prefix() == ""
            assert page.tail_fee_usd.spin.prefix() == ""
            assert page.tail_fee_rmb.spin.suffix() == ""
            assert page.tail_fee_usd.spin.suffix() == ""
            rmb_symbol = page._root.findChild(QLabel, "lblTailSettingsRmbSymbol")
            usd_symbol = page._root.findChild(QLabel, "lblTailSettingsUsdSymbol")
            assert rmb_symbol is not None and rmb_symbol.text() == "¥"
            assert usd_symbol is not None and usd_symbol.text() == "$"
            page.tail_fee_usd.setValue(5.55)
            page._sync_tail_rmb_from_usd(recalculate=False)
            rate = float(page.settings.get("exchange_rate_usd_to_rmb", 7.2))
            assert page.tail_fee_rmb.value() == round(5.55 * rate, 2)
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_cost_summary_tail_rmb_only_and_total_rmb_usd(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            assert page.system_rows["tail"].text().startswith("¥")
            assert "$" not in page.system_rows["tail"].text()
            assert page.system_total.text().startswith("¥")
            assert page.system_total_usd.isVisibleTo(page._root)
            assert page.system_total_usd.text().startswith("$")
            rate = float(page.settings.get("exchange_rate_usd_to_rmb", 7.2))
            assert page.system_total_usd.text() == f"${page.current_system_cost / rate:.2f}"
        finally:
            page.deleteLater()
            qapp.processEvents()

    @staticmethod
    def _visible_cost_names(page) -> list[str]:
        layout = page._root.findChild(QVBoxLayout, "systemCostLayout")
        names: list[str] = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            row = item.layout() if item is not None else None
            if row is None:
                widget = item.widget() if item is not None else None
                if widget is not None:
                    row = widget.layout()
            if row is None:
                continue
            for j in range(row.count()):
                widget = row.itemAt(j).widget()
                if isinstance(widget, QLabel) and not widget.isHidden():
                    names.append(widget.text())
        allowed = {"采购成本", "国内运费", "头程（深圳）", "头程（义乌）", "头程（—）",
                   "服务费", "尾程", "总成本"}
        return [name for name in names if name in allowed]

    def test_cost_summary_strict_order_and_forwarder_switch(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            expected = ["采购成本", "国内运费", "头程（深圳）", "服务费", "尾程", "总成本"]
            assert self._visible_cost_names(page) == expected
            # 切换货代后头程名切换为（义乌）
            yiwu = next(
                item for item in page.context.settings_service.load()["forwarders"]
                if item["name"] == "义乌货代"
            )
            page.selected_forwarder_id = yiwu["id"]
            page.recalculate()
            expected_switch = ["采购成本", "国内运费", "头程（义乌）", "服务费", "尾程", "总成本"]
            assert self._visible_cost_names(page) == expected_switch
            # 头程值只显示金额，货代名不再悬浮在中间
            assert page.system_rows["first_mile"].text().startswith("¥")
            assert "深圳货代" not in page.system_rows["first_mile"].text()
            assert "义乌货代" not in page.system_rows["first_mile"].text()
        finally:
            page.deleteLater()
            qapp.processEvents()


# ---------------------------------------------------------------------------
# 历史表：列数、分隔线、列宽、顶部对齐
# ---------------------------------------------------------------------------


class TestHistoryTableRound5:
    def test_still_eight_columns(self, qapp, temp_context):
        page = HistoryPage(temp_context)
        try:
            assert page.table.columnCount() == 8
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_calibration_column_stretch_stage3_final(self, qapp, temp_context):
        page = HistoryPage(temp_context)
        try:
            header = page.table.horizontalHeader()
            assert header.stretchLastSection() is False
            assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
            # 阶段 3 最终调整：包装列固定收窄，释放宽度给校准内容列（Stretch）
            assert header.sectionResizeMode(6) == QHeaderView.ResizeMode.Fixed
            assert header.sectionResizeMode(7) == QHeaderView.ResizeMode.Stretch
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_vertical_separator_stylesheet_present(self, qapp, temp_context):
        page = HistoryPage(temp_context)
        try:
            stylesheet = page.table.styleSheet()
            assert "border-right" in stylesheet
            assert "1px solid" in stylesheet
            # 不出现横向滚动条
            assert page.table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_text_columns_still_top_aligned(self, qapp, temp_context):
        payload = {
            "product_name": "分隔线测试商品",
            "product_link": "",
            "created_at": "2026-08-09T00:00:00Z",
            "updated_at": "2026-08-09T01:00:00Z",
            "product_cost_rmb": 18.8,
            "domestic_shipping_rmb": 5.0,
            "shein_quote_usd": 30.0,
            "layers": {
                "adopted": {
                    "selected_packaging": "保守档",
                    "conservative": {
                        "packaging_method": "气泡袋",
                        "length_cm": 27,
                        "width_cm": 17,
                        "height_cm": 4,
                        "weight_g": 30,
                    },
                },
                "calculated": {
                    "system_cost_rmb": 390.37,
                    "exchange_rate": 7.2,
                    "forwarder_name": "深圳货代",
                    "logistics_quote": {
                        "weight_fee_rmb": 316.54,
                        "fixed_fee_rmb": 10.0,
                        "tail_fee_rmb": 40.03,
                        "total_logistics_rmb": 366.57,
                    },
                },
            },
            "profit_scenarios": {
                "no_activity": {"sale_price_usd": 30.0, "profit_rmb": 20.0},
            },
        }
        temp_context.record_service.save(payload, images=[], ai_initial=None)
        page = HistoryPage(temp_context)
        try:
            assert page.table.rowCount() == 1
            for col in (2, 3, 4, 5, 6, 7):
                container = page.table.cellWidget(0, col)
                assert container is not None
                assert isinstance(container.layout(), QVBoxLayout)
        finally:
            page.deleteLater()
            qapp.processEvents()
