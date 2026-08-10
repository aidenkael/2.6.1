"""阶段 3 最后一次综合调整：历史/摘要联动 + HistoryPage 最终 UI。

覆盖任务书：
- 十七：历史/摘要联动（完整摘要保存/首段显示/恢复/AI首次不变）；
- 十九：HistoryPage 最终 UI（总成本加粗与 ¥/$ 格式、保存汇率快照、
  售价三行顺序与右对齐、利润标题、包装/校准列宽、长反馈截断+tooltip、
  无横向滚动条）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.pages.history_page import HistoryPage, _display_product_name

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _payload(product_name: str) -> dict:
    return {
        "product_name": product_name,
        "product_link": "https://detail.1688.com/offer/demo.html",
        "product_cost_rmb": 66.80,
        "domestic_shipping_rmb": 28.00,
        "shein_quote_usd": 30.0,
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "normal": {
                    "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                    "height_cm": 17, "weight_g": 720,
                },
                "conservative": {
                    "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                    "height_cm": 17, "weight_g": 720,
                },
                "bare": {"length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580},
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
            "driver": "no_activity_price",
            "no_activity": {
                "sale_price_usd": 30.0, "profit_rmb": 78.74,
                "profit_rate_on_cost": 0.5, "rule_status": {},
            },
            "activity": {
                "sale_price_usd": 27.0, "profit_rmb": 55.12,
                "profit_rate_on_cost": 0.35, "rule_status": {},
            },
        },
    }


def _ai_initial() -> dict:
    return {
        "model": "test-model",
        "observation": {"product_name": "睡帽", "display_product_summary": "睡帽；软布结构；可压缩"},
        "adopted_packaging": {
            "normal": {
                "packaging_method": "气泡袋", "length_cm": 17, "width_cm": 32,
                "height_cm": 17, "weight_g": 720,
            }
        },
    }


def _create(context, product_name: str) -> str:
    return context.record_service.save(
        _payload(product_name), images=[], ai_initial=_ai_initial(),
    )


def _row_for(page: HistoryPage, record_id: str) -> int:
    for row in range(page.table.rowCount()):
        item = page.table.item(row, 0)
        if item is not None and item.data(256) == record_id:
            return row
    raise AssertionError(f"record {record_id} not in table")


def _name_label(page: HistoryPage, row: int) -> QLabel:
    widget = page.table.cellWidget(row, 2)
    labels = widget.findChildren(QLabel)
    return labels[0]


def _kv_labels(page: HistoryPage, row: int, column: int) -> list[QLabel]:
    """kv 单元格内 QLabel 按布局顺序：key0 value0 key1 value1 ..."""
    widget = page.table.cellWidget(row, column)
    rows = []
    column_layout = widget.layout()
    for i in range(column_layout.count()):
        row_widget = column_layout.itemAt(i).widget()
        if row_widget is None:
            continue
        row_labels = row_widget.findChildren(QLabel)
        if row_labels:
            rows.extend(row_labels)
    return rows


# ---------------------------------------------------------------- 十七 联动


class TestSummaryHistoryLink:
    def test_a_full_summary_saved_name_shows_first_segment_restore_full(self, qapp, context):
        """A：完整摘要保存；历史名称只显示首段；重新打开恢复完整摘要。"""
        record_id = _create(context, "睡帽；软布结构；可压缩")
        # 底层完整摘要仍存在
        stored = context.store.load_record(record_id)
        assert stored["product_name"] == "睡帽；软布结构；可压缩"
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        assert _name_label(page, row).text() == "睡帽"
        page.deleteLater()
        # 重新打开记录：新品测算页恢复完整摘要
        from profit_accounting_26.ui.pages import CalculationPage

        calc = CalculationPage(context)
        try:
            calc.load_record_payload(record_id)
            assert calc.product_summary.text() == "睡帽；软布结构；可压缩"
        finally:
            calc.deleteLater()

    def test_b_summary_without_separator_shows_full(self, qapp, context):
        """B：摘要只有“睡帽”：历史名称仍为“睡帽”。"""
        record_id = _create(context, "睡帽")
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        assert _name_label(page, row).text() == "睡帽"
        page.deleteLater()

    def test_c_user_edited_summary_saved_and_restored(self, qapp, context):
        """C：用户把摘要从 A 改成 B：历史名称显示 B，重新打开恢复完整 B 摘要。"""
        record_id = _create(context, "A；硬质；不可压缩")
        updated = _payload("B；软质；可压缩")
        context.record_service.save(
            updated, images=[], ai_initial=None, record_id=record_id,
        )
        stored = context.store.load_record(record_id)
        assert stored["product_name"] == "B；软质；可压缩"
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        assert _name_label(page, row).text() == "B"
        page.deleteLater()
        from profit_accounting_26.ui.pages import CalculationPage

        calc = CalculationPage(context)
        try:
            calc.load_record_payload(record_id)
            assert calc.product_summary.text() == "B；软质；可压缩"
        finally:
            calc.deleteLater()

    def test_d_ai_initial_not_modified_by_save_or_reopen(self, qapp, context):
        """D：保存/重开不得修改 AI首次 ai_initial。"""
        record_id = _create(context, "睡帽；软布结构；可压缩")
        before = context.history_record_v2_service.load_v2(record_id).ai_initial
        updated = _payload("睡帽；软布结构；可压缩；用户补充")
        context.record_service.save(updated, images=[], ai_initial=None, record_id=record_id)
        after = context.history_record_v2_service.load_v2(record_id).ai_initial
        assert after == before
        assert after["observation"]["product_name"] == "睡帽"

    def test_empty_summary_keeps_unnamed_fallback(self):
        assert _display_product_name("") == "未命名商品"
        assert _display_product_name("   ") == "未命名商品"
        assert _display_product_name("睡帽") == "睡帽"
        assert _display_product_name("睡帽；软布结构") == "睡帽"


# ---------------------------------------------------------------- 十九 HistoryPage


class TestHistoryPageFinalUi:
    def test_total_cost_key_bold_and_rmb_usd_format(self, qapp, context):
        """1+2：总成本字段名加粗；金额格式 ¥RMB / $USD（保存汇率 7.2）。"""
        record_id = _create(context, "睡帽")
        page = HistoryPage(context)
        try:
            row = _row_for(page, record_id)
            labels = _kv_labels(page, row, 3)
            keys = labels[0::2]
            values = labels[1::2]
            assert keys[0].text() == "总成本"
            assert "font-weight" in keys[0].styleSheet() and "600" in keys[0].styleSheet()
            # 其余三行字段名不加粗
            for key_label in keys[1:]:
                assert "font-weight" not in key_label.styleSheet()
            assert values[0].text() == "¥237.26 / $32.95"
        finally:
            page.deleteLater()

    def test_total_cost_uses_saved_rate_not_current_settings(self, qapp, context):
        """3：总成本 USD 用保存汇率快照，不受当前设置汇率变化影响。"""
        record_id = _create(context, "睡帽")
        settings = context.settings_service.load()
        settings["exchange_rate_usd_to_rmb"] = 8.0
        context.settings_service.save(settings)
        page = HistoryPage(context)
        try:
            row = _row_for(page, record_id)
            values = _kv_labels(page, row, 3)[1::2]
            assert values[0].text() == "¥237.26 / $32.95"
        finally:
            page.deleteLater()

    def test_total_cost_without_valid_rate_shows_dash_usd(self, qapp, context):
        """无有效汇率快照：¥50.93 / $—，不按当前汇率补算。"""
        payload = _payload("睡帽")
        payload["layers"]["calculated"].pop("exchange_rate")
        record_id = context.record_service.save(payload, images=[], ai_initial=_ai_initial())
        page = HistoryPage(context)
        try:
            row = _row_for(page, record_id)
            values = _kv_labels(page, row, 3)[1::2]
            assert values[0].text() == "¥237.26 / $—"
        finally:
            page.deleteLater()

    def test_price_order_and_right_alignment(self, qapp, context):
        """4+5：售价顺序 SHEIN标价/活动售价/SHEIN核价；数值右对齐。"""
        record_id = _create(context, "睡帽")
        page = HistoryPage(context)
        try:
            row = _row_for(page, record_id)
            labels = _kv_labels(page, row, 4)
            keys = labels[0::2]
            values = labels[1::2]
            assert [key.text() for key in keys] == ["SHEIN标价", "活动售价", "SHEIN核价"]
            assert [value.text() for value in values] == ["$30.00", "$27.00", "$30.00"]
            for value in values:
                assert value.alignment() & Qt.AlignmentFlag.AlignRight
        finally:
            page.deleteLater()

    def test_profit_titles(self, qapp, context):
        """6：利润两行标题为 标价利润 / 活动利润。"""
        record_id = _create(context, "睡帽")
        page = HistoryPage(context)
        try:
            row = _row_for(page, record_id)
            labels = _kv_labels(page, row, 5)
            keys = labels[0::2]
            assert [key.text() for key in keys] == ["标价利润", "活动利润"]
            values = labels[1::2]
            assert values[0].text() == "¥78.74 / 50.00%"
            assert values[1].text() == "¥55.12 / 35.00%"
        finally:
            page.deleteLater()

    def test_packaging_narrower_calibration_wider(self, qapp, context):
        """7+8：包装数据列比原 195px 更窄；校准内容列获得更多宽度。"""
        _create(context, "睡帽")
        page = HistoryPage(context)
        try:
            page.resize(1660, 900)
            qapp.processEvents()
            packaging = page.table.columnWidth(6)
            calibration = page.table.columnWidth(7)
            assert packaging == 150 < 195
            assert calibration > packaging
            assert calibration > 170  # 原校准列固定 170px
        finally:
            page.deleteLater()

    def test_long_feedback_truncated_with_tooltip(self, qapp, context):
        """9+10：长反馈不无限撑高；截断 + …；tooltip 为完整反馈。"""
        record_id = _create(context, "睡帽")
        long_note = "这个商品的实际包装与AI判断完全不同。" * 40  # 约 760 字
        service = context.calibration_feedback_service
        feedback_id = service.save({"record_id": record_id, "user_note": long_note})
        context.history_record_v2_service.link_feedback(record_id, feedback_id)
        page = HistoryPage(context)
        try:
            page.resize(1660, 900)
            row = _row_for(page, record_id)
            widget = page.table.cellWidget(row, 7)
            label = widget.findChild(QLabel)
            display = label.text()
            assert display.endswith("…")
            assert len(display) <= 100
            assert label.toolTip() == page._calibration_text(page.records[row])
            assert long_note in label.toolTip()
            # 行高不被几百字反馈无限撑高（3 行以内 + 边距）
            assert page.table.rowHeight(row) <= 120
        finally:
            page.deleteLater()

    def test_no_horizontal_scrollbar(self, qapp, context):
        """11：无横向滚动条。"""
        _create(context, "睡帽")
        page = HistoryPage(context)
        try:
            assert page.table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        finally:
            page.deleteLater()
