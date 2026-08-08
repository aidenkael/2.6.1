"""HistoryExportService 测试：Full/Calibration 导出、range、防重复导出、脱敏。"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.application.history_export_service import (
    ExportAbortError,
    HistoryExportService,
    _assert_safe_arcname,
    sanitize_for_export,
)
from profit_accounting_26.storage import SQLiteStore


@pytest.fixture()
def env(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    feedback = CalibrationFeedbackService(store)
    feedback.initialize()
    exporter = HistoryExportService(store, feedback, data_dir=tmp_path)
    return store, feedback, exporter, tmp_path


def _record(store, name: str, *, secret: bool = False) -> str:
    payload = {
        "product_name": name,
        "product_link": "",
        "images": [{"relative_path": f"images/{name}/01_ab.png", "sha256": "ab" * 32,
                      "original_name": "IMG_0001.png"}],
        "layers": {
            "ai_raw": {"observation": {"length_cm": 10}, "model": "m-1"},
            "adopted": {"bare": {"weight_g": 50}, "selected_packaging": "正常档",
                          "normal": {"packaging_method": "袋装", "length_cm": 11, "width_cm": 9,
                                       "height_cm": 2, "weight_g": 60}},
            "calculated": {"profit_rmb": 2.0, "packaging_engine_version": "v2"},
        },
        "profit_scenarios": {"no_activity": {"profit_rmb": 2.0}},
    }
    if secret:
        payload["layers"]["ai_raw"]["authorization"] = "Bearer abc123"
        payload["layers"]["ai_raw"]["api_key"] = "secret-value"
        payload["debug_path"] = r"C:\Users\SecretUser\Pictures\IMG_0001.png"
    return store.save_new_record(payload)


def test_full_export_zip_structure(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "商品A")
    feedback.save({"record_id": record_id, "user_note": "可以压缩"})
    target = exporter.export_full(tmp_path / "history-export-v1.zip")
    assert target.is_file()
    with zipfile.ZipFile(target) as bundle:
        names = set(bundle.namelist())
        assert names == {"manifest.json", "records.json", "feedback.json"}
        manifest = json.loads(bundle.read("manifest.json"))
        records = json.loads(bundle.read("records.json"))["records"]
        feedback_items = json.loads(bundle.read("feedback.json"))["items"]
    assert manifest["format"] == "history-export-v1"
    assert manifest["include_images"] is False
    assert manifest["record_count"] == 1
    # 默认不复制图片二进制，只保留 metadata/hash
    assert manifest["images"][0]["sha256"] == "ab" * 32
    assert records[0]["product_name"] == "商品A"
    assert feedback_items[0]["user_note"] == "可以压缩"


def test_calibration_export_structure_and_summary(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "商品B")
    feedback.save({
        "record_id": record_id, "user_note": "提手可以折下去",
        "structure": {"can_fold": True, "foldable_parts": ["handle"]},
        "suggested_package": {"length_cm": 20},
    })
    target = exporter.export_calibration(tmp_path / "calibration-feedback-v1.zip")
    with zipfile.ZipFile(target) as bundle:
        assert set(bundle.namelist()) == {"manifest.json", "feedback.json", "records_summary.json"}
        manifest = json.loads(bundle.read("manifest.json"))
        summaries = json.loads(bundle.read("records_summary.json"))["summaries"]
        items = json.loads(bundle.read("feedback.json"))["items"]
    assert manifest["format"] == "calibration-feedback-v1"
    assert manifest["prompt_version"]
    assert manifest["software_version"] == "2.6.1"
    assert manifest["model"] == "m-1"
    assert manifest["rule_version"] == "v2"
    summary = summaries[0]
    assert summary["record_id"] == record_id
    assert summary["product_name"] == "商品B"
    assert summary["bare_facts"] == {"weight_g": 50}
    assert summary["legacy_packaging_output"]["normal"]["packaging_method"] == "袋装"
    assert summary["image_hashes"] == ["ab" * 32]
    assert items[0]["user_note"] == "提手可以折下去"


def test_manifest_versions_from_actual_record_sources(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "模型A")
    payload = store.load_record(record_id)
    payload["layers"]["ai_raw"] = {
        "observation": {"model": "obs-model-1", "prompt_version": "p1"},
    }
    payload["layers"]["calculated"]["packaging_engine_version"] = "engine-1"
    store.update_record(record_id, payload)
    feedback.save({"record_id": record_id, "user_note": "a"})

    second_id = _record(store, "模型B")
    second = store.load_record(second_id)
    second["layers"]["ai_raw"] = {"model": "top-model-2"}
    second["layers"]["calculated"]["packaging_engine_version"] = "engine-2"
    store.update_record(second_id, second)
    feedback.save({"record_id": second_id, "user_note": "b"})

    target = exporter.export_calibration(tmp_path / "multi.zip")
    with zipfile.ZipFile(target) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
    # 同时兼容 observation.model 与顶层 model 两种实际落位
    assert manifest["model"] == ["obs-model-1", "top-model-2"]
    assert manifest["rule_version"] == ["engine-1", "engine-2"]


def test_manifest_versions_null_when_unavailable(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "无版本")
    payload = store.load_record(record_id)
    payload["layers"]["ai_raw"] = {}
    payload["layers"]["calculated"].pop("packaging_engine_version", None)
    store.update_record(record_id, payload)
    feedback.save({"record_id": record_id, "user_note": "a"})
    target = exporter.export_calibration(tmp_path / "null.zip")
    with zipfile.ZipFile(target) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
    assert manifest["model"] is None
    assert manifest["rule_version"] is None


def test_export_marks_feedback_exported_but_allows_reexport(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "商品C")
    feedback_id = feedback.save({"record_id": record_id, "user_note": "反馈"})
    exporter.export_calibration(tmp_path / "c1.zip")
    exported = feedback.load(feedback_id)
    assert exported.calibration_exported_at
    assert exported.calibration_export_batch_id
    # 不阻止再次导出
    exporter.export_calibration(tmp_path / "c2.zip")
    assert feedback.load(feedback_id).calibration_export_batch_id != exported.calibration_export_batch_id


def test_export_range_record_ids_and_time(env):
    store, feedback, exporter, tmp_path = env
    a = _record(store, "甲")
    b = _record(store, "乙")
    target = exporter.export_full(tmp_path / "r.zip", mode="record_ids", record_ids=[a])
    with zipfile.ZipFile(target) as bundle:
        records = json.loads(bundle.read("records.json"))["records"]
    assert [record["id"] for record in records] == [a]
    with pytest.raises(ValueError):
        exporter.export_full(tmp_path / "bad.zip", mode="no_such_mode")
    # created_at range：给一个极早的 after 则全部命中，极晚则无
    all_records = exporter.select_records(mode="created_at_range", created_after="0000")
    assert {record["id"] for record in all_records} == {a, b}
    assert exporter.select_records(mode="created_at_range", created_after="9999") == []
    assert len(exporter.select_records(mode="updated_at_range", updated_after="0000")) == 2


def test_unexported_calibration_only_range(env):
    store, feedback, exporter, tmp_path = env
    a = _record(store, "有反馈")
    b = _record(store, "无反馈")
    c = _record(store, "已导出反馈")
    d = _record(store, "已导出又修改")
    feedback.save({"record_id": a, "user_note": "新反馈"})
    exported_id = feedback.save({"record_id": c, "user_note": "旧反馈"})
    feedback.mark_exported([exported_id], batch_id="batch-old")
    modified_id = feedback.save({"record_id": d, "user_note": "v1"})
    feedback.mark_exported([modified_id], batch_id="batch-old")
    feedback.save({"feedback_id": modified_id, "record_id": d, "user_note": "v2"})
    selected = exporter.select_records(mode="all", unexported_calibration_only=True)
    assert {record["id"] for record in selected} == {a, d}
    assert b not in {record["id"] for record in selected}
    assert c not in {record["id"] for record in selected}


def test_unexported_calibration_only_full_cycle(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "完整周期")
    feedback_id = feedback.save({"record_id": record_id, "user_note": "首次保存"})

    # 首次保存后出现在待导出集合
    selected = exporter.select_records(mode="all", unexported_calibration_only=True)
    assert record_id in {record["id"] for record in selected}

    # 首次导出后不再出现，且导出状态已记录
    exporter.export_calibration(tmp_path / "first.zip")
    exported = feedback.load(feedback_id)
    assert exported.calibration_exported_at
    assert exported.calibration_export_batch_id
    assert exported.feedback_updated_after_export is False
    selected = exporter.select_records(mode="all", unexported_calibration_only=True)
    assert record_id not in {record["id"] for record in selected}

    # 导出后修改：标记更新，并重新出现在待导出集合
    feedback.save({"feedback_id": feedback_id, "record_id": record_id, "user_note": "修改后"})
    updated = feedback.load(feedback_id)
    assert updated.feedback_updated_after_export is True
    selected = exporter.select_records(mode="all", unexported_calibration_only=True)
    assert record_id in {record["id"] for record in selected}

    # 第二次导出：导出状态更新、标记恢复 false、不再出现在待导出集合
    exporter.export_calibration(tmp_path / "second.zip")
    reexported = feedback.load(feedback_id)
    assert reexported.calibration_exported_at >= exported.calibration_exported_at
    assert reexported.calibration_export_batch_id != exported.calibration_export_batch_id
    assert reexported.feedback_updated_after_export is False
    selected = exporter.select_records(mode="all", unexported_calibration_only=True)
    assert record_id not in {record["id"] for record in selected}


def test_sanitization_strips_secrets_and_paths(env):
    store, feedback, exporter, tmp_path = env
    _record(store, "含敏感", secret=True)
    target = exporter.export_full(tmp_path / "s.zip")
    with zipfile.ZipFile(target) as bundle:
        text = "".join(bundle.read(name).decode("utf-8")
                       for name in ("manifest.json", "records.json", "feedback.json"))
    assert "secret-value" not in text
    assert "Bearer" not in text
    assert "SecretUser" not in text
    assert "IMG_0001.png" in text  # 路径只保留文件名
    # 直接函数级校验
    cleaned = sanitize_for_export({"api_key": "x", "nested": {"token": "y", "ok": 1},
                                     "path": r"C:\Users\U\a.jpg"})
    assert cleaned == {"nested": {"ok": 1}, "path": "a.jpg"}


def test_export_aborts_when_secret_pattern_remains(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "泄漏")
    payload = store.load_record(record_id)
    payload["layers"]["ai_raw"]["note"] = "sk-" + "a" * 40  # sanitize 不识别值内容
    store.update_record(record_id, payload)
    with pytest.raises(ExportAbortError):
        exporter.export_full(tmp_path / "leak.zip")
    assert not (tmp_path / "leak.zip").exists()


def test_include_images_copies_originals_safely(env):
    store, feedback, exporter, tmp_path = env
    record_id = _record(store, "带图")
    # 在 data_dir 内放一个与 relative_path 匹配的文件
    image_dir = tmp_path / "images" / "带图"
    image_dir.mkdir(parents=True)
    (image_dir / "01_ab.png").write_bytes(b"fake-image-bytes")
    target = exporter.export_full(tmp_path / "img.zip", mode="record_ids",
                                   record_ids=[record_id], include_images=True)
    with zipfile.ZipFile(target) as bundle:
        assert "images/01_ab.png" in bundle.namelist()
        assert bundle.read("images/01_ab.png") == b"fake-image-bytes"
    # 文件缺失时安全跳过
    (image_dir / "01_ab.png").unlink()
    target2 = exporter.export_full(tmp_path / "img2.zip", mode="record_ids",
                                    record_ids=[record_id], include_images=True)
    with zipfile.ZipFile(target2) as bundle:
        assert "images/01_ab.png" not in bundle.namelist()


def test_arcname_traversal_rejected():
    with pytest.raises(ExportAbortError):
        _assert_safe_arcname("../evil.json")
    with pytest.raises(ExportAbortError):
        _assert_safe_arcname(r"C:\abs.json")
    with pytest.raises(ExportAbortError):
        _assert_safe_arcname("/etc/passwd")
    _assert_safe_arcname("records.json")
    _assert_safe_arcname("images/a.png")
