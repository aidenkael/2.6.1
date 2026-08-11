"""Stage 4 验收：HistoryPage 标价利率修正 + 列宽调整 + 加粗样式。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.ui.pages.history_page import HistoryPage

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _payload_with_scenarios() -> dict:
    """双场景记录：总成本 100、标价利润 40、活动利润 25。"""
    return {
        "product_name": "测试商品",
        "product_link": "https://detail.1688.com/offer/demo.html",
        "product_cost_rmb": 50.0,
        "domestic_shipping_rmb": 10.0,
        "shein_quote_usd": 20.0,
        "layers": {
            "adopted": {
                "selected_packaging": "标准档",
                "normal": {
                    "packaging_method": "气泡袋",
                    "length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580,
                },
                "bare": {"length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580},
            },
            "calculated": {
                "system_cost_rmb": 100.0,
                "exchange_rate": 7.2,
                "forwarder_name": "测试货代",
                "logistics_quote": {
                    "weight_fee_rmb": 30.0,
                    "fixed_fee_rmb": 10.0,
                    "tail_fee_rmb": 10.0,
                    "total_logistics_rmb": 50.0,
                },
            },
        },
        # 关键：双场景记录，no_activity 没有 profit_rate_on_cost，需要计算
        "profit_scenarios": {
            "schema_version": 1,
            "driver": "no_activity_price",
            "calculation_total_cost_rmb": 100.0,
            "exchange_rate": 7.2,
            "reserve_percent": 0,
            "applied_rule_ids": [],
            "applied_rules": [],
            "selected_rule_id": "",
            "legacy_compatible": False,
            "no_activity": {
                "sale_price_usd": 20.0,
                "sale_price_rmb": 144.0,
                "profit_rmb": 40.0,  # 标价利润 40
                "profit_usd": 5.56,
                # 注意：没有 profit_rate_on_cost，需要从 profit_rmb / cost 计算
                "rule_status": {},
            },
            "activity": {
                "sale_price_usd": 18.0,
                "sale_price_rmb": 129.6,
                "profit_rmb": 25.0,  # 活动利润 25
                "profit_usd": 3.47,
                "profit_rate_on_cost": 0.25,  # 活动利率 25%（小数形式）
                "rule_status": {},
            },
        },
    }


def _ai_initial() -> dict:
    return {
        "model": "test-model",
        "observation": {"product_name": "测试商品", "display_product_summary": "测试商品"},
        "adopted_packaging": {
            "normal": {
                "packaging_method": "气泡袋",
                "length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580,
            }
        },
    }


def _create(context) -> str:
    return context.record_service.save(
        _payload_with_scenarios(), images=[], ai_initial=_ai_initial(),
    )


def _row_for(page: HistoryPage, record_id: str) -> int:
    for row in range(page.table.rowCount()):
        item = page.table.item(row, 0)
        if item is not None and item.data(256) == record_id:
            return row
    raise AssertionError(f"record {record_id} not in table")


def _kv_labels(page: HistoryPage, row: int, column: int) -> list[QLabel]:
    """kv 单元格内 QLabel 按布局顺序：key0 value0 key1 value1 ..."""
    widget = page.table.cellWidget(row, column)
    labels = []
    column_layout = widget.layout()
    for i in range(column_layout.count()):
        row_widget = column_layout.itemAt(i).widget()
        if row_widget is None:
            continue
        row_labels = row_widget.findChildren(QLabel)
        if row_labels:
            labels.extend(row_labels)
    return labels


class TestProfitRateCorrection:
    """标价利率修正：新双场景记录用 profit_rmb / cost 计算，不 fallback 到活动利率。"""

    def test_list_price_rate_differs_from_activity_rate(self, qapp, context):
        """标价利润率与活动利润率不同：40/100=40%，25/100=25%。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        # 列 5 = 利润列
        labels = _kv_labels(page, row, 5)
        # labels: [标价利润, 值, 活动利润, 值]
        assert labels[0].text() == "标价利润"
        assert "40.00%" in labels[1].text(), f"标价利率应为 40%，实际: {labels[1].text()}"
        assert labels[2].text() == "活动利润"
        assert "25.00%" in labels[3].text(), f"活动利率应为 25%，实际: {labels[3].text()}"

    def test_list_price_rate_from_saved_profit_divided_by_saved_cost(self, qapp, context):
        """标价利率来自保存时利润 / 保存时总成本，不读取当前设置重新计算。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        labels = _kv_labels(page, row, 5)
        # 标价利润值应包含 ¥40.00 / 40.00%
        assert "¥40.00" in labels[1].text()
        assert "40.00%" in labels[1].text()


class TestColumnWidths:
    """列宽调整：成本 235、包装 185、利润 200。"""

    def test_cost_column_width_is_235(self, qapp, context):
        """成本列宽度 = 235px。"""
        page = HistoryPage(context)
        assert page.table.columnWidth(3) == 235

    def test_packaging_column_width_is_185(self, qapp, context):
        """包装数据列宽度 = 185px。"""
        page = HistoryPage(context)
        assert page.table.columnWidth(6) == 185

    def test_profit_column_width_is_200(self, qapp, context):
        """利润列宽度 = 200px。"""
        page = HistoryPage(context)
        assert page.table.columnWidth(5) == 200


class TestBoldTitles:
    """售价/利润列关键标题加粗。"""

    def test_shein_list_price_title_is_bold(self, qapp, context):
        """售价列：SHEIN标价 标题加粗。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        # 列 4 = 售价列
        labels = _kv_labels(page, row, 4)
        # labels: [SHEIN标价, 值, 活动售价, 值, SHEIN核价, 值]
        shein_label = next(l for l in labels if l.text() == "SHEIN标价")
        assert "font-weight: 600" in shein_label.styleSheet()

    def test_activity_sale_price_title_is_bold(self, qapp, context):
        """售价列：活动售价 标题加粗。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        labels = _kv_labels(page, row, 4)
        activity_label = next(l for l in labels if l.text() == "活动售价")
        assert "font-weight: 600" in activity_label.styleSheet()

    def test_shein_quote_price_title_is_not_bold(self, qapp, context):
        """售价列：SHEIN核价 保持普通字体。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        labels = _kv_labels(page, row, 4)
        quote_label = next(l for l in labels if l.text() == "SHEIN核价")
        assert "font-weight" not in quote_label.styleSheet()

    def test_list_price_profit_title_is_bold(self, qapp, context):
        """利润列：标价利润 标题加粗。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        # 列 5 = 利润列
        labels = _kv_labels(page, row, 5)
        list_price_label = next(l for l in labels if l.text() == "标价利润")
        assert "font-weight: 600" in list_price_label.styleSheet()

    def test_activity_profit_title_is_bold(self, qapp, context):
        """利润列：活动利润 标题加粗。"""
        record_id = _create(context)
        page = HistoryPage(context)
        row = _row_for(page, record_id)
        labels = _kv_labels(page, row, 5)
        activity_label = next(l for l in labels if l.text() == "活动利润")
        assert "font-weight: 600" in activity_label.styleSheet()
