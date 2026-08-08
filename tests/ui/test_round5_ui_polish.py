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
# AI估算包装方式中文化（仅显示层）
# ---------------------------------------------------------------------------


class TestPackagingMethodChinese:
    def test_polybag_shows_chinese_on_ai_card_only(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            page.apply_proposal(_proposal("polybag"))
            assert page.normal_fields["method"].text() == "塑料袋包装"
            # 当前采用后台字段保留原始英文，不污染数据
            assert page.conservative_fields["method"].text() == "polybag"
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_box_and_bubble_mailer_mapping(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            page._fill_package_fields(page.normal_fields, {"packaging_method": "box"})
            assert page.normal_fields["method"].text() == "纸箱包装"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "bubble mailer"})
            assert page.normal_fields["method"].text() == "气泡袋包装"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "vacuum bag"})
            assert page.normal_fields["method"].text() == "真空袋包装"
            page._fill_package_fields(page.normal_fields, {"packaging_method": "bag"})
            assert page.normal_fields["method"].text() == "袋装"
            # 未知英文值不崩溃，显示“其他包装”
            page._fill_package_fields(page.normal_fields, {"packaging_method": "strange_method_xyz"})
            assert page.normal_fields["method"].text() == "其他包装"
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
            assert left_bottom.minimumHeight() == right_bottom.minimumHeight() == 84
            assert left_bottom.maximumHeight() == right_bottom.maximumHeight() == 84
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
# 用户修正动态物流提示
# ---------------------------------------------------------------------------


class TestForwarderHint:
    def test_hint_shows_forwarder_and_weight_fee_only(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            hint = page.user_correction_hint
            assert hint is not None
            assert "深圳货代" in hint.text()
            assert "纯头程" in hint.text()
            assert f"¥{page.current_quote.weight_fee_rmb:.2f}" in hint.text()
            # 只含 weight_fee_rmb，不含固定服务费
            assert "服务费" not in hint.text()
            assert f"¥{page.current_quote.fixed_fee_rmb:.2f}" not in hint.text()
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_hint_refreshes_on_forwarder_switch(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            before = page.user_correction_hint.text()
            assert "深圳货代" in before
            yiwu = next(
                item for item in page.context.settings_service.load()["forwarders"]
                if item["name"] == "义乌货代"
            )
            page.selected_forwarder_id = yiwu["id"]
            page.recalculate()
            after = page.user_correction_hint.text()
            assert "义乌货代" in after
            assert f"¥{page.current_quote.weight_fee_rmb:.2f}" in after
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_hint_refreshes_on_adopted_weight_change(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            before = page.user_correction_hint.text()
            page.conservative_fields["weight"].setValue(900.0)
            page.recalculate()
            assert page.user_correction_hint.text() != before
            assert f"¥{page.current_quote.weight_fee_rmb:.2f}" in page.user_correction_hint.text()
        finally:
            page.deleteLater()
            qapp.processEvents()

    def test_hint_never_pollutes_note_or_calibration_dirty(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            _arm_page(page)
            assert page.user_correction.text() == ""
            assert page.user_calibration_dirty is False
            assert page.user_correction_hint.text() != "当前：纯头程 —"
            # 提示刷新不写 user_note、不置用户校准 dirty
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
    def test_tail_rmb_readonly_usd_editable_and_rate_linked(self, qapp, temp_context):
        page = CalculationPage(temp_context)
        try:
            assert page.tail_fee_rmb.spin.isReadOnly() is True
            assert page.tail_fee_usd.spin.isReadOnly() is False
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

    def test_calibration_column_not_stretch(self, qapp, temp_context):
        page = HistoryPage(temp_context)
        try:
            header = page.table.horizontalHeader()
            assert header.stretchLastSection() is False
            assert header.sectionResizeMode(7) != QHeaderView.ResizeMode.Stretch
            assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
            assert header.sectionResizeMode(6) == QHeaderView.ResizeMode.Stretch
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
