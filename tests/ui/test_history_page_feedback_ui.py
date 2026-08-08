"""HistoryPage 单一大表格：8 视觉列 / 两缩略图 / 来源链接 / 本地搜索 / 软删除。

覆盖任务书第 18-22、26-29 项：
- HistoryPage 只有 8 个视觉主列；
- 两个缩略图位置固定，第二图缺失显示占位；
- 原始链接不新增独立列；
- 搜索“挂绳”命中本地近义词商品；
- 成本/售价/利润读取保存快照，不重新计算；
- 未实测与已实测在历史页状态区分；
- 软删除不删除图片；
- 旧 2.6.1 / 旧 V2 记录仍可打开；
- recordRequested 返回主页链路不变。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.ui.pages.history_page import HistoryPage, expand_search_terms

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _v2_payload(product_name: str = "蝴蝶结手机挂绳") -> dict:
    return {
        "product_name": product_name,
        "product_link": f"https://detail.1688.com/offer/{product_name}.html",
        "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T01:00:00Z",
        "product_cost_rmb": 66.80,
        "domestic_shipping_rmb": 28.00,
        "shein_quote_usd": 30.0,
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
        "model": "gpt-test",
        "observation": {"display_product_summary": "软包挂绳"},
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


def _create_v2(context, *, product_name: str = "蝴蝶结手机挂绳", images=None, ai_initial=None) -> str:
    return context.record_service.save(
        _v2_payload(product_name),
        images=images or [],
        ai_initial=ai_initial if ai_initial is not None else _ai_initial(),
    )


def _create_legacy(context, record_id: str = "legacy-1", product_name: str = "旧商品") -> str:
    payload = {
        "id": record_id,
        "product_name": product_name,
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-01T00:00:00Z",
        "layers": {
            "adopted": {
                "selected_packaging": "正常档",
                "normal": {
                    "packaging_method": "纸箱",
                    "length_cm": 30,
                    "width_cm": 20,
                    "height_cm": 10,
                    "weight_g": 200,
                },
            },
            "calculated": {
                "sale_price_usd": 25.0,
                "profit_rmb": 8.0,
                "exchange_rate": 7.2,
                "profit_rate_percent": 20.0,
            },
        },
        "profit_scenarios": {
            "no_activity": {"sale_price_usd": 25.0, "profit_rmb": 8.0},
        },
    }
    context.store.save_new_record(payload)
    return record_id


def _make_png(path: Path) -> Path:
    image = QImage(24, 24, QImage.Format.Format_RGB32)
    image.fill(0xFFCC6644)
    assert image.save(str(path), "PNG")
    return path


def _row_for(page: HistoryPage, record_id: str) -> int:
    for row in range(page.table.rowCount()):
        item = page.table.item(row, 0)
        if item is not None and item.data(256) == record_id:
            return row
    raise AssertionError(f"record {record_id} not in table")


def _cell_label(page: HistoryPage, row: int, column: int) -> QLabel:
    widget = page.table.cellWidget(row, column)
    assert isinstance(widget, QLabel)
    return widget


# ---------------------------------------------------------------- 18. 8 列


def test_table_has_exactly_eight_visual_columns(qapp, context):
    _create_v2(context)
    page = HistoryPage(context)
    assert page.table.columnCount() == 8
    headers = [page.table.horizontalHeaderItem(i).text() for i in range(8)]
    assert headers == ["序号", "图片", "名称", "成本", "售价", "利润", "包装数据", "校准内容"]
    # 不存在“最后修改时间”列
    assert not any("时间" in text for text in headers)


def test_index_column_is_display_order_not_record_id(qapp, context):
    first = _create_v2(context, product_name="商品甲")
    _create_v2(context, product_name="商品乙")
    page = HistoryPage(context)
    indices = [page.table.item(row, 0).text() for row in range(page.table.rowCount())]
    assert indices == ["1", "2"]
    assert page.table.item(_row_for(page, first), 0).text() in ("1", "2")


# ---------------------------------------------------------------- 19. 缩略图


def test_two_fixed_thumbnail_slots_with_placeholder(qapp, context, tmp_path):
    png1 = _make_png(tmp_path / "a.png")
    image = SessionImage(png1, ImageType.MAIN, "sha-a", png1.name)
    record_id = _create_v2(context, images=[image])
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    cell = page.table.cellWidget(row, 1)
    buttons = cell.findChildren(QPushButton)
    # 固定两个缩略图位置：第二张缺失也必须是等尺寸占位框
    assert len(buttons) == 2
    assert buttons[0].iconSize() == buttons[1].iconSize()
    assert not buttons[0].icon().isNull()
    assert not buttons[1].icon().isNull()


def test_no_images_row_keeps_two_placeholders(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    cell = page.table.cellWidget(row, 1)
    buttons = cell.findChildren(QPushButton)
    assert len(buttons) == 2
    assert all(not button.isEnabled() or not button.icon().isNull() for button in buttons)


def test_thumbnail_reads_thumbnail_key_with_fallback(qapp, context, tmp_path):
    png = _make_png(tmp_path / "img.png")
    image = SessionImage(png, ImageType.MAIN, "sha-placeholder", png.name)
    record_id = _create_v2(context, images=[image])
    page = HistoryPage(context)
    v2 = context.history_record_v2_service.load_v2(record_id)
    item = v2.images[0]
    assert item.get("thumbnail_key")
    thumbnail = page._image_path(item, prefer_thumbnail=True)
    original = page._image_path(item, prefer_thumbnail=False)
    assert thumbnail is not None and thumbnail.is_file()
    assert "thumbnails" in thumbnail.as_posix()
    assert original is not None and original.is_file()
    assert thumbnail != original


# ---------------------------------------------------------------- 20. 名称与链接


def test_link_shown_under_name_without_extra_column(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    cell = page.table.cellWidget(row, 2)
    link_edit = cell.findChild(QLineEdit)
    assert link_edit is not None
    assert link_edit.isReadOnly()
    assert link_edit.text().startswith("https://detail.1688.com/offer/")
    # 名称列显示短名称
    name_label = cell.findChild(QLabel)
    assert name_label.text() == "蝴蝶结手机挂绳"


def test_missing_link_shows_dash(qapp, context):
    payload = _v2_payload("无链接商品")
    payload["product_link"] = ""
    record_id = context.record_service.save(payload, images=[], ai_initial=_ai_initial())
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    cell = page.table.cellWidget(row, 2)
    assert cell.findChild(QLineEdit) is None
    labels = cell.findChildren(QLabel)
    assert any(label.text() == "—" for label in labels)


# ---------------------------------------------------------------- 22. 快照列


def test_cost_column_reads_saved_snapshot(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    text = _cell_label(page, row, 3).text()
    assert "总成本    ¥237.26" in text
    assert "国内成本  ¥66.80 + ¥28.00" in text
    assert "头程      深圳货代  ¥92.48 + ¥10.00" in text
    assert "尾程      $5.55 / ¥39.98" in text


def test_price_and_profit_columns_read_saved_snapshot(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    price = _cell_label(page, row, 4).text()
    assert "核价      $30.00" in price
    assert "标价      $30.00" in price
    assert "活动后    $27.00" in price
    profit = _cell_label(page, row, 5).text()
    assert "普通      ¥78.74 / 50.00%" in profit
    assert "活动      ¥55.12 / 35.00%" in profit


def test_legacy_record_profit_falls_back_safely(qapp, context):
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    row = _row_for(page, legacy_id)
    profit = _cell_label(page, row, 5).text()
    assert "普通      ¥8.00 / 20.00%" in profit


def test_packaging_column_shows_bare_ai_current(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    row = _row_for(page, record_id)
    text = _cell_label(page, row, 6).text()
    assert "裸品    45×30×15 / 580g" in text
    assert "AI      17×32×17 / 720g" in text
    assert "当前    17×32×17 / 720g" in text


def test_legacy_record_ai_column_not_faked(qapp, context):
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    row = _row_for(page, legacy_id)
    text = _cell_label(page, row, 6).text()
    assert "AI      —" in text
    assert "当前    30×20×10 / 200g" in text


# ---------------------------------------------------------------- 26. 校准状态


def test_calibration_states_uncalibrated_corrected_measured(qapp, context):
    uncalibrated = _create_v2(context, product_name="商品未校准")
    corrected = _create_v2(context, product_name="商品已修正")
    measured = _create_v2(context, product_name="商品已实测")
    service = context.calibration_feedback_service
    fid_corrected = service.save({"record_id": corrected, "user_note": "肩带可拆"})
    context.history_record_v2_service.link_feedback(corrected, fid_corrected)
    fid_measured = service.save(
        {
            "record_id": measured,
            "user_note": "实测更小",
            "actual_logistics": {
                "actual_package_dimensions": {"length_cm": 23, "width_cm": 14, "height_cm": 3},
                "actual_package_weight_g": 560,
                "evidence_level": "actual_measured",
            },
        }
    )
    context.history_record_v2_service.link_feedback(measured, fid_measured)
    page = HistoryPage(context)
    assert _cell_label(page, _row_for(page, uncalibrated), 7).text() == "未校准"
    corrected_text = _cell_label(page, _row_for(page, corrected), 7).text()
    assert corrected_text.startswith("已修正·待实测")
    assert "肩带可拆" in corrected_text
    measured_text = _cell_label(page, _row_for(page, measured), 7).text()
    assert measured_text.startswith("已校准")
    assert "实际 23×14×3 / 560g" in measured_text


# ---------------------------------------------------------------- 21. 本地搜索


def test_synonym_expansion_contains_group_terms():
    terms = expand_search_terms("挂绳")
    for expected in ("挂绳", "手机绳", "腕带", "手机链", "挂饰", "挂件", "包挂"):
        assert expected in terms


def test_search_lanyard_matches_synonym_product(qapp, context):
    _create_v2(context, product_name="可爱手机链坠")
    _create_v2(context, product_name="普通水杯")
    page = HistoryPage(context)
    page.search.setText("挂绳")
    assert page.table.rowCount() == 1
    name_cell = page.table.cellWidget(0, 2)
    assert "手机链" in name_cell.findChild(QLabel).text()


def test_search_matches_record_id_and_link(qapp, context):
    record_id = _create_v2(context, product_name="商品甲")
    page = HistoryPage(context)
    page.search.setText(record_id)
    assert page.table.rowCount() == 1
    page.search.setText("detail.1688.com")
    assert page.table.rowCount() == 1
    page.search.setText("")
    assert page.table.rowCount() == 1


# ---------------------------------------------------------------- 27. 软删除


def test_soft_delete_hides_record_and_keeps_images(qapp, context, tmp_path, monkeypatch):
    import PySide6.QtWidgets as qw

    monkeypatch.setattr(qw.QMessageBox, "question", lambda *a, **k: qw.QMessageBox.StandardButton.Yes)
    png = _make_png(tmp_path / "keep.png")
    image = SessionImage(png, ImageType.MAIN, "sha-keep", png.name)
    record_id = _create_v2(context, images=[image])
    page = HistoryPage(context)
    v2 = context.history_record_v2_service.load_v2(record_id)
    original_path = page._image_path(v2.images[0], prefer_thumbnail=False)
    assert original_path is not None and original_path.is_file()
    page.table.selectRow(_row_for(page, record_id))
    page._archive_selected()
    # 从正常列表消失
    assert page.table.rowCount() == 0
    # 图片文件保留（不做 GC、不物理删除）
    assert original_path.is_file()
    # 记录本体仍在库中，只是 status=archived
    raw = context.record_service.load(record_id)
    assert raw["status"] == "archived"


def test_action_buttons_disabled_without_selection(qapp, context):
    page = HistoryPage(context)
    assert page.table.rowCount() == 0
    assert not page.open_button.isEnabled()
    assert not page.calibrate_button.isEnabled()
    assert not page.delete_button.isEnabled()


# ---------------------------------------------------------------- 28-29. 兼容与链路


def test_legacy_and_v2_records_both_listed(qapp, context):
    v2_id = _create_v2(context, product_name="新商品A")
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    assert page.table.rowCount() == 2
    names = {
        page.table.cellWidget(_row_for(page, v2_id), 2).findChild(QLabel).text(),
        page.table.cellWidget(_row_for(page, legacy_id), 2).findChild(QLabel).text(),
    }
    assert names == {"新商品A", "旧商品"}


def test_record_requested_signal_and_double_click(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    received: list[str] = []
    page.recordRequested.connect(received.append)
    row = _row_for(page, record_id)
    page.table.selectRow(row)
    page.open_selected()
    assert received == [record_id]
    page.table.cellDoubleClicked.emit(row, 1)
    assert received == [record_id, record_id]
