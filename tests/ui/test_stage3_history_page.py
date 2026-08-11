"""阶段 3：历史记录页 UI 微调。

覆盖：
- 删除历史页副标题“裸品 → AI估算 → 当前采用 → 保存 → 用户校准”；
- 新增“导出校准反馈”按钮，位于搜索框之前；
- 成本列四行 key/value：总成本 / 国内成本 / 总头程（深圳|义乌）/ 尾程；
- 总头程 = 保存的 weight_fee + fixed_fee，深圳货代→深圳、义乌货代→义乌；
- 尾程使用保存的 tail + 保存时汇率快照（修改当前汇率不影响旧记录）；
- 利润列“标价利润 / 活动利润”读取保存的 profit_scenarios（修改当前规则不影响）；
- 成本列加宽、包装数据列缩窄。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext, SettingsService
from profit_accounting_26.ui.pages.history_page import HistoryPage

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _payload(product_name: str = "测试商品", forwarder: str = "深圳货代") -> dict:
    return {
        "product_name": product_name,
        "product_link": f"https://detail.1688.com/offer/{product_name}.html",
        "product_cost_rmb": 66.80,
        "domestic_shipping_rmb": 28.00,
        "layers": {
            "adopted": {
                "selected_packaging": "保守档",
                "normal": {
                    "packaging_method": "气泡袋",
                    "length_cm": 17,
                    "width_cm": 32,
                    "height_cm": 17,
                    "weight_g": 720,
                },
                "conservative": {
                    "packaging_method": "气泡袋",
                    "length_cm": 17,
                    "width_cm": 32,
                    "height_cm": 17,
                    "weight_g": 720,
                },
                "bare": {"length_cm": 45, "width_cm": 30, "height_cm": 15, "weight_g": 580},
            },
            "calculated": {
                "system_cost_rmb": 237.26,
                "exchange_rate": 7.2,
                "forwarder_name": forwarder,
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
                "sale_price_usd": 30.0,
                "profit_rmb": 78.74,
                "profit_rate_on_cost": 0.5,
                "rule_status": {},
            },
            "activity": {
                "sale_price_usd": 27.0,
                "profit_rmb": 55.12,
                "profit_rate_on_cost": 0.35,
                "rule_status": {},
            },
        },
    }


def _ai_initial() -> dict:
    return {
        "observation": {"product_name": "AI首次简名"},
        "adopted_packaging": {
            "normal": {
                "packaging_method": "气泡袋",
                "length_cm": 17,
                "width_cm": 32,
                "height_cm": 17,
                "weight_g": 720,
            }
        },
    }


def _create(context, *, forwarder: str = "深圳货代", product_name: str = "测试商品") -> str:
    return context.record_service.save(
        _payload(product_name=product_name, forwarder=forwarder),
        images=[],
        ai_initial=_ai_initial(),
    )


def _row_for(page: HistoryPage, record_id: str) -> int:
    for row in range(page.table.rowCount()):
        item = page.table.item(row, 0)
        if item is not None and item.data(256) == record_id:
            return row
    raise AssertionError(f"record {record_id} not in table")


def _cell_text(page: HistoryPage, row: int, column: int) -> str:
    widget = page.table.cellWidget(row, column)
    labels = widget.findChildren(QLabel) if widget is not None else []
    return "\n".join(label.text() for label in labels)


def test_history_subtitle_removed(qapp, context):
    """删除副标题：历史页不再出现“裸品 → AI估算 → …”。"""
    _create(context)
    page = HistoryPage(context)
    try:
        texts = [label.text() for label in page.findChildren(QLabel)]
        assert "裸品 → AI估算 → 当前采用 → 保存 → 用户校准" not in texts
    finally:
        page.deleteLater()


def test_export_button_exists_before_search(qapp, context):
    """导出校准反馈按钮存在且位于搜索框之前。"""
    _create(context)
    page = HistoryPage(context)
    try:
        export_button = page.export_button
        assert isinstance(export_button, QPushButton)
        assert export_button.text() == "导出校准反馈"
        layout = page._header_right_layout
        export_index = layout.indexOf(export_button)
        search_index = layout.indexOf(page.search)
        assert 0 <= export_index < search_index, "导出按钮必须在搜索框之前"
    finally:
        page.deleteLater()


def test_cost_column_wider_than_packaging(qapp, context):
    """成本列加宽、包装数据列缩窄。"""
    _create(context)
    page = HistoryPage(context)
    try:
        assert page.table.columnWidth(3) > page.table.columnWidth(6)
        # Stage 4 验收：成本列从 250px 调整为 235px
        assert page.table.columnWidth(3) == 235
    finally:
        page.deleteLater()


@pytest.mark.parametrize("forwarder,expected", [("深圳货代", "总头程（深圳）"), ("义乌货代", "总头程（义乌）")])
def test_total_first_mile_label_compresses_forwarder(qapp, context, forwarder, expected):
    """深圳货代→深圳、义乌货代→义乌；金额 = weight_fee + fixed_fee。"""
    record_id = _create(context, forwarder=forwarder)
    page = HistoryPage(context)
    try:
        row = _row_for(page, record_id)
        text = _cell_text(page, row, 3)
        assert expected in text
        assert "¥102.48" in text  # 92.48 + 10.00
    finally:
        page.deleteLater()


def test_custom_forwarder_not_renamed(qapp, context):
    """其它自定义货代不擅自改名。"""
    record_id = _create(context, forwarder="物流专线A")
    page = HistoryPage(context)
    try:
        row = _row_for(page, record_id)
        text = _cell_text(page, row, 3)
        assert "总头程（物流专线A）" in text
    finally:
        page.deleteLater()


def test_tail_uses_saved_exchange_rate_snapshot(qapp, context):
    """尾程使用保存时 tail + 保存时汇率；修改当前汇率后旧记录显示不变。"""
    record_id = _create(context)
    page1 = HistoryPage(context)
    row = _row_for(page1, record_id)
    before = _cell_text(page1, row, 3)
    assert "¥39.98 / $5.55" in before
    page1.deleteLater()

    settings = context.settings_service.load()
    settings["exchange_rate_usd_to_rmb"] = 8.0  # 修改当前汇率
    context.settings_service.save(settings)

    page2 = HistoryPage(context)
    row2 = _row_for(page2, record_id)
    after = _cell_text(page2, row2, 3)
    assert "¥39.98 / $5.55" in after, "旧记录尾程不得按当前汇率重算"
    page2.deleteLater()


def test_profit_uses_saved_snapshot_not_current_rules(qapp, context):
    """利润列读取保存的 profit_scenarios；修改当前利润规则后旧记录不变。"""
    record_id = _create(context)
    page1 = HistoryPage(context)
    row = _row_for(page1, record_id)
    before = _cell_text(page1, row, 5)
    assert "标价利润" in before and "¥78.74 / 50.00%" in before
    assert "活动利润" in before and "¥55.12 / 35.00%" in before
    page1.deleteLater()

    settings = context.settings_service.load()
    settings["profit_rules"] = []  # 删除当前规则
    context.settings_service.save(settings)

    page2 = HistoryPage(context)
    row2 = _row_for(page2, record_id)
    after = _cell_text(page2, row2, 5)
    assert "¥78.74 / 50.00%" in after and "¥55.12 / 35.00%" in after
    page2.deleteLater()


def test_forwarder_saved_with_settings_service_still_reads_snapshot(qapp, context):
    """货代名称来自保存快照，不来自当前 SettingsService。"""
    record_id = _create(context, forwarder="深圳货代")
    settings = context.settings_service.load()
    settings["forwarders"] = []
    context.settings_service.save(settings)
    page = HistoryPage(context)
    try:
        row = _row_for(page, record_id)
        assert "总头程（深圳）" in _cell_text(page, row, 3)
    finally:
        page.deleteLater()


def test_export_dataset_all_pending_ignore_search_range_uses_visible(qapp, context, tmp_path):
    """all/pending 不受搜索框影响；range 使用当前可见记录；archived 不导出。"""
    ids = [_create(context, product_name=name) for name in ("商品A", "商品B", "商品C")]
    # 归档记录：all/pending 不得包含
    archived_payload = _payload("已归档商品")
    archived_payload["status"] = "archived"
    archived_id = context.record_service.save(
        archived_payload, images=[], ai_initial=_ai_initial()
    )

    page = HistoryPage(context)
    try:
        page.search.setText("商品A")
        page.refresh()
        assert len(page.records) == 1
        assert page.records[0]["id"] == ids[0]

        all_dataset = page._export_dataset("all")
        pending_dataset = page._export_dataset("pending")
        assert len(all_dataset) == 3 and len(pending_dataset) == 3
        dataset_ids = {str(payload["id"]) for payload in all_dataset}
        assert dataset_ids == set(ids)
        assert archived_id not in dataset_ids

        # range 使用当前可见记录：显示序号 1 → 商品A
        range_dataset = page._export_dataset("range")
        assert len(range_dataset) == 1
        result = context.calibration_export_service.export(
            range_dataset, "range", tmp_path, seq_range="1-1"
        )
        assert result.record_ids == [ids[0]]
    finally:
        page.deleteLater()
