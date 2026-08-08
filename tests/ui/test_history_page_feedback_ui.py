"""HistoryPage 面向普通用户：列表字段 / 缩略图 / 反馈状态 / 结构化详情 / 返回测算页。"""

from __future__ import annotations

from pathlib import Path

import pytest

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.ui.pages.history_page import HistoryPage

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QLabel  # noqa: E402


@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _v2_payload(product_name: str = "新商品A") -> dict:
    return {
        "product_name": product_name,
        "product_link": f"https://example.com/{product_name}",
        "created_at": "2026-08-08T00:00:00Z",
        "updated_at": "2026-08-08T01:00:00Z",
        "layers": {
            "adopted": {
                "selected_packaging": "正常档",
                "normal": {
                    "packaging_method": "气泡袋",
                    "length_cm": 20,
                    "width_cm": 15,
                    "height_cm": 3,
                    "weight_g": 120,
                },
                "conservative": {
                    "packaging_method": "纸箱",
                    "length_cm": 22,
                    "width_cm": 17,
                    "height_cm": 5,
                    "weight_g": 180,
                },
                "bare": {"length_cm": 18, "width_cm": 13, "height_cm": 2, "weight_g": 100},
            },
            "calculated": {"profit_rmb": 12.5, "exchange_rate": 7.2, "profit_rate_percent": 25.0},
        },
        "profit_scenarios": {
            "driver": "no_activity_price",
            "no_activity": {
                "sale_price_usd": 30.0,
                "profit_rmb": 12.5,
                "profit_usd": 1.7,
                "rule_status": {},
            },
            "activity": {
                "sale_price_usd": 27.0,
                "profit_rmb": 9.8,
                "profit_rate_on_cost": 0.18,
                "rule_status": {"rules": [{"name": "SHEIN 29美元以下运费补贴"}]},
            },
        },
    }


def _create_v2(context, *, product_name: str = "新商品A", images=None, ai_initial=None) -> str:
    return context.record_service.save(
        _v2_payload(product_name),
        images=images or [],
        ai_initial=ai_initial
        or {
            "model": "gpt-test",
            "observation": {"display_product_summary": "可压缩软包"},
        },
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


def test_page_shows_legacy_and_v2_records(qapp, context):
    v2_id = _create_v2(context, product_name="新商品A")
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    page.refresh()
    assert page.table.rowCount() == 2
    names = {page.table.item(_row_for(page, v2_id), 1).text(), page.table.item(_row_for(page, legacy_id), 1).text()}
    assert names == {"新商品A", "旧商品"}


def test_v2_thumbnail_reads_thumbnail_key(qapp, context, tmp_path):
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


def test_no_thumbnail_falls_back_to_compat_image_path(qapp, context, tmp_path):
    target_dir = context.paths.data_dir / "images" / "originals" / "ab"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = _make_png(target_dir / "legacy.png")
    payload = {
        "id": "legacy-img",
        "product_name": "带兼容图记录",
        "created_at": "2026-07-01T00:00:00Z",
        "updated_at": "2026-07-01T00:00:00Z",
        "images": [
            {
                "relative_path": "images/originals/ab/legacy.png",
                "image_type": "主图",
                "order": 0,
                "original_name": "legacy.png",
                "sha256": "legacy-hash",
            }
        ],
        "layers": {"adopted": {"selected_packaging": "正常档"}, "calculated": {}},
    }
    context.store.save_new_record(payload)
    page = HistoryPage(context)
    v2 = context.history_record_v2_service.load_v2("legacy-img")
    path = page._image_path(v2.images[0], prefer_thumbnail=True)
    assert path == target
    assert path.is_file()


def test_no_images_does_not_crash(qapp, context):
    _create_v2(context)
    page = HistoryPage(context)
    page.show_details()
    labels = page.details_body.findChildren(QLabel)
    assert any("无图片" in label.text() for label in labels)


def test_no_feedback_shows_weifankui_status(qapp, context):
    record_id = _create_v2(context)
    page = HistoryPage(context)
    page.refresh()
    row = _row_for(page, record_id)
    assert page.table.item(row, 5).text() == "未反馈"


def test_feedback_status_flow(qapp, context):
    record_id = _create_v2(context)
    service = context.calibration_feedback_service
    feedback_id = service.save({"record_id": record_id, "user_note": "v1"})
    context.history_record_v2_service.link_feedback(record_id, feedback_id)
    page = HistoryPage(context)
    page.refresh()
    row = _row_for(page, record_id)
    assert page.table.item(row, 5).text() == "已反馈"
    service.mark_exported([feedback_id], batch_id="batch-1")
    page.refresh()
    assert page.table.item(row, 5).text() == "已导出"
    service.save({"feedback_id": feedback_id, "record_id": record_id, "user_note": "v2"})
    page.refresh()
    assert page.table.item(row, 5).text() == "已更新 · 待导出"


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


def test_details_ai_initial_v2_and_legacy(qapp, context):
    v2_id = _create_v2(context)
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    page.table.selectRow(_row_for(page, v2_id))
    page.show_details()
    assert "gpt-test" in page._detail_values["ai_model"].text()
    assert "可压缩软包" in page._detail_values["ai_summary"].text()
    page.table.selectRow(_row_for(page, legacy_id))
    page.show_details()
    assert "旧记录" in page._detail_values["ai_note"].text()


def test_profit_snapshot_shown_from_stored_values(qapp, context):
    v2_id = _create_v2(context)
    legacy_id = _create_legacy(context)
    page = HistoryPage(context)
    page.refresh()
    assert page.table.item(_row_for(page, v2_id), 4).text() == "¥12.50"
    assert page.table.item(_row_for(page, legacy_id), 4).text() == "¥8.00"
    page.table.selectRow(_row_for(page, v2_id))
    page.show_details()
    assert page._detail_values["profit_no_activity"].text() == "¥12.50"
    assert page._detail_values["profit_activity"].text() == "¥9.80"
    assert "补贴" in page._detail_values["profit_hint"].text()
