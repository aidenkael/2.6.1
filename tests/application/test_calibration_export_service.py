"""阶段 3：校准反馈导出 V1 服务测试。

覆盖：
- Sheet1 严格 8 列、Sheet2 技术元数据；
- 商品简名 / AI首次发货估算 / 用户校准 / 实际物流 / 真实头程 的真实来源；
- current_estimate 不得进入导出；
- 图片多原图复制、相对路径、thumbnail fallback warning、完全缺失报错；
- 全部 / 自定义范围 / 未导出 三种模式；
- 失败事务不标记已导出；删除记录后旧状态不崩溃；legacy 兼容。
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QBuffer  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calibration_export_service import (
    CONTRACT_VERSION,
    CalibrationFeedbackExporter,
    ExportIncompleteError,
    ExportStateStore,
    SHEET1_COLUMNS,
    SHEET2_COLUMNS,
    first_ai_short_name,
    first_ai_shipment_text,
    parse_seq_range,
)

@pytest.fixture()
def context(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PROFIT_ACCOUNTING_DATA_DIR", str(tmp_path))
    return AppContext.create_default()


def _png_bytes() -> bytes:
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("#336699"))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _payload(product_name: str = "测试商品", *, forwarder: str = "深圳货代") -> dict:
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


def _ai_initial(*, product_name: str = "AI首次简名") -> dict:
    return {
        "observation": {
            "product_name": product_name,
            "raw_payload": {
                "shipment": {
                    "length_cm": 25,
                    "width_cm": 20,
                    "height_cm": 5,
                    "weight_g": 600,
                    "state": "可压缩；袋装发货",
                }
            },
        },
        "external_ai_packaging_proposal": {
            "normal": {
                "packaging_method": "可压缩；袋装发货",
                "length_cm": 25,
                "width_cm": 20,
                "height_cm": 5,
                "weight_g": 600,
            }
        },
        "adopted_packaging": {
            "normal": {
                "packaging_method": "可压缩；袋装发货",
                "length_cm": 25,
                "width_cm": 20,
                "height_cm": 5,
                "weight_g": 600,
            }
        },
    }


def _create_v2(context, *, product_name: str = "测试商品", ai_initial=None, images=None) -> str:
    payload = _payload(product_name)
    if images is not None:
        payload["images"] = images
    return context.history_record_v2_service.create_record(
        payload,
        ai_initial=ai_initial if ai_initial is not None else _ai_initial(),
    )


def _image_refs(context, count: int = 1) -> list[dict]:
    refs = []
    for index in range(count):
        reference = context.image_store.add_bytes(
            _png_bytes(), suffix=".png", original_filename=f"img{index}.png"
        )
        refs.append(
            {
                **reference.to_dict(),
                "order": index,
                "relative_path": reference.storage_key,
            }
        )
    return refs


def _load_workbook(path: Path):
    from openpyxl import load_workbook

    return load_workbook(path)


class TestExportShape:
    def test_sheet1_exactly_eight_columns(self, context, tmp_path):
        _create_v2(context)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        sheet = workbook["校准反馈"]
        assert sheet.max_column == 8
        assert [cell.value for cell in sheet[1]] == list(SHEET1_COLUMNS)

    def test_sheet2_metadata_and_contract_version(self, context, tmp_path):
        record_id = _create_v2(context)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        info = workbook["导出信息"]
        assert [cell.value for cell in info[1]] == list(SHEET2_COLUMNS)
        row2 = [cell.value for cell in info[2]]
        assert row2[0] == record_id
        assert row2[1] == result.batch_id
        assert row2[4] == CONTRACT_VERSION

    def test_export_state_file_structure(self, context, tmp_path):
        record_id = _create_v2(context)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        state_path = context.paths.data_dir / "calibration" / "export_state.json"
        assert state_path.is_file()
        store = ExportStateStore(context.paths.data_dir)
        assert record_id in store.exported_record_ids()
        assert result.record_ids == [record_id]


class TestExportSources:
    def test_first_ai_short_name_not_overwritten_by_current_name(self, context, tmp_path):
        _create_v2(context, product_name="用户后来改的名称", ai_initial=_ai_initial(product_name="AI首次简名"))
        records = context.record_service.list()
        assert first_ai_short_name(records[0]) == "AI首次简名"
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].cell(2, 2).value == "AI首次简名"

    def test_legacy_short_name_empty(self, context, tmp_path):
        payload = _payload("旧商品")
        record_id = context.history_record_v2_service.create_record(
            payload, ai_initial=None, record_id="legacy-export-1"
        )
        records = [context.store.load_record(record_id)]
        assert first_ai_short_name(records[0]) == ""
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].cell(2, 2).value in ("", "—")

    def test_ai_first_shipment_uses_ai_initial_not_current_estimate(self, context, tmp_path):
        _create_v2(context)
        records = context.record_service.list()
        # 当前采用与 AI 首次不同：导出必须用 AI 首次
        text = first_ai_shipment_text(records[0])
        assert "25×20×5 / 600g" in text
        assert "可压缩；袋装发货" in text
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].cell(2, 5).value == "25×20×5 / 600g\n可压缩；袋装发货"

    def test_user_calibration_only_user_note_and_suggested(self, context, tmp_path):
        record_id = _create_v2(context)
        service = context.calibration_feedback_service
        feedback_id = service.save(
            {
                "record_id": record_id,
                "user_note": "正常袋装即可，不需要盒装",
                "suggested_package": {
                    "length_cm": 25, "width_cm": 20, "height_cm": 4, "weight_g": 550,
                },
            }
        )
        context.history_record_v2_service.link_feedback(record_id, feedback_id)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        cell = workbook["校准反馈"].cell(2, 6).value
        assert "用户反馈：正常袋装即可，不需要盒装" in cell
        assert "建议包装：25×20×4 / 550g" in cell

    def test_actual_logistics_empty_when_no_actual(self, context, tmp_path):
        record_id = _create_v2(context)
        service = context.calibration_feedback_service
        feedback_id = service.save({"record_id": record_id, "user_note": "只有文字反馈"})
        context.history_record_v2_service.link_feedback(record_id, feedback_id)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].cell(2, 7).value in (None, "")
        assert workbook["校准反馈"].cell(2, 8).value in (None, "")

    def test_actual_logistics_and_first_mile_use_actual_layer(self, context, tmp_path):
        record_id = _create_v2(context)
        service = context.calibration_feedback_service
        feedback_id = service.save(
            {
                "record_id": record_id,
                "user_note": "实测",
                "actual_logistics": {
                    "actual_package_dimensions": {"length_cm": 24, "width_cm": 19, "height_cm": 4},
                    "actual_package_weight_g": 530,
                    "actual_chargeable_weight_kg": 0.53,
                    "actual_packaging_method": "袋装",
                    "actual_forwarder": "深圳",
                    "actual_first_mile_fee_rmb": 26.0,
                    "evidence_level": "actual_measured",
                },
            }
        )
        context.history_record_v2_service.link_feedback(record_id, feedback_id)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        actual = workbook["校准反馈"].cell(2, 7).value
        assert "实际包装：24×19×4 cm" in actual
        assert "实际重量：530g" in actual
        assert "实际计费重：0.53kg" in actual
        assert "实际包装方式：袋装" in actual
        assert workbook["校准反馈"].cell(2, 8).value == "深圳 / ¥26.00"


class TestExportImages:
    def test_all_originals_copied_with_relative_paths(self, context, tmp_path):
        refs = _image_refs(context, count=2)
        record_id = _create_v2(context, images=refs)
        records = [context.store.load_record(record_id)]
        result = context.calibration_export_service.export(records, "all", tmp_path)
        images_dir = result.output_dir / "images"
        assert (images_dir / "001_1.png").is_file()
        assert (images_dir / "001_2.png").is_file()
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        cell = workbook["校准反馈"].cell(2, 4).value
        assert cell == "images/001_1.png\nimages/001_2.png"
        info = workbook["导出信息"].cell(2, 4).value
        assert "images/001_1.png" in info

    def test_thumbnail_fallback_records_warning(self, context, tmp_path):
        ref = _image_refs(context, count=1)[0]
        record_id = _create_v2(context, images=[ref])
        # 删除原图，只保留缩略图
        (context.paths.data_dir / ref["storage_key"]).unlink()
        records = [context.store.load_record(record_id)]
        result = context.calibration_export_service.export(records, "all", tmp_path)
        assert result.warnings, "缩略图 fallback 必须产生 warning"
        assert (result.output_dir / "images" / "001_1.jpg").is_file()

    def test_missing_original_and_thumbnail_fails_without_mark(self, context, tmp_path):
        ref = _image_refs(context, count=1)[0]
        record_id = _create_v2(context, images=[ref])
        (context.paths.data_dir / ref["storage_key"]).unlink()
        thumbnail = ref.get("thumbnail_key")
        if thumbnail:
            (context.paths.data_dir / thumbnail).unlink(missing_ok=True)
        records = [context.store.load_record(record_id)]
        with pytest.raises(ExportIncompleteError):
            context.calibration_export_service.export(records, "all", tmp_path)
        store = ExportStateStore(context.paths.data_dir)
        assert record_id not in store.exported_record_ids()

    def test_record_without_images_allowed(self, context, tmp_path):
        record_id = _create_v2(context, images=[])
        records = [context.store.load_record(record_id)]
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].cell(2, 4).value in (None, "")


class TestExportModes:
    def _three_records(self, context) -> list[str]:
        ids = []
        for name in ("商品A", "商品B", "商品C"):
            ids.append(_create_v2(context, product_name=name))
        return ids

    def test_all_mode_allows_reexport(self, context, tmp_path):
        ids = self._three_records(context)
        records = context.record_service.list()
        first = context.calibration_export_service.export(records, "all", tmp_path / "a")
        second = context.calibration_export_service.export(records, "all", tmp_path / "b")
        assert len(first.record_ids) == 3 and len(second.record_ids) == 3
        assert all(record_id in ExportStateStore(context.paths.data_dir).exported_record_ids() for record_id in ids)

    def test_range_mode_maps_display_seq_to_record_id(self, context, tmp_path):
        ids = self._three_records(context)
        records = context.record_service.list()
        result = context.calibration_export_service.export(
            records, "range", tmp_path, seq_range="2-3"
        )
        # 显示序号 2、3 → 对应列表第 2、3 条
        assert result.record_ids == [records[1]["id"], records[2]["id"]]

    def test_range_parse_and_validation(self):
        assert parse_seq_range("1-30", 30) == (1, 30)
        assert parse_seq_range("3-5", 10) == (3, 5)
        for bad in ("", "abc", "5-3", "0-3", "1-99", "1 2"):
            with pytest.raises(ValueError):
                parse_seq_range(bad, 30)

    def test_pending_mode_filters_exported(self, context, tmp_path):
        ids = self._three_records(context)
        records = context.record_service.list()
        first = context.calibration_export_service.export(records, "range", tmp_path / "a", seq_range="1-1")
        assert first.record_ids == [records[0]["id"]]
        pending = context.calibration_export_service.export(records, "pending", tmp_path / "b")
        assert records[0]["id"] not in pending.record_ids
        assert set(pending.record_ids) == {records[1]["id"], records[2]["id"]}


class TestFailureAndLifecycle:
    def test_deleted_record_stale_state_does_not_crash(self, context, tmp_path):
        record_id = _create_v2(context, product_name="待删除")
        records = context.record_service.list()
        context.calibration_export_service.export(records, "all", tmp_path / "a")
        context.record_service.delete_record(record_id)
        other_id = _create_v2(context, product_name="保留商品")
        records = context.record_service.list()
        # 旧状态里有已删除的 record_id，不影响后续导出
        result = context.calibration_export_service.export(records, "pending", tmp_path / "b")
        assert other_id in result.record_ids

    def test_excel_write_failure_does_not_mark(self, context, tmp_path, monkeypatch):
        record_id = _create_v2(context)
        records = context.record_service.list()

        def _boom(*_args, **_kwargs):
            raise OSError("模拟 Excel 写入失败")

        monkeypatch.setattr(
            context.calibration_export_service,
            "_write_excel",
            _boom,
        )
        with pytest.raises(ExportIncompleteError):
            context.calibration_export_service.export(records, "all", tmp_path)
        assert record_id not in ExportStateStore(context.paths.data_dir).exported_record_ids()

    def test_legacy_record_export_compatible(self, context, tmp_path):
        payload = _payload("旧商品")
        record_id = context.history_record_v2_service.create_record(
            payload, ai_initial=None, record_id="legacy-export-2"
        )
        records = [context.store.load_record(record_id)]
        result = context.calibration_export_service.export(records, "all", tmp_path)
        workbook = _load_workbook(result.output_dir / "校准反馈.xlsx")
        assert workbook["校准反馈"].max_column == 8
        assert workbook["校准反馈"].cell(2, 2).value in ("", "—")
        assert workbook["校准反馈"].cell(2, 5).value in (None, "")

    def test_exported_at_and_batch_id_written_per_record(self, context, tmp_path):
        record_id = _create_v2(context)
        records = context.record_service.list()
        result = context.calibration_export_service.export(records, "all", tmp_path)
        state = ExportStateStore(context.paths.data_dir).load()["records"]
        assert state[record_id]["export_batch_id"] == result.batch_id
        assert state[record_id]["exported_at"] == result.exported_at
