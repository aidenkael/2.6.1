"""History V2 Production Bridge 测试：RecordService → ImageStore + HistoryRecordV2Service。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from profit_accounting_26.application.data_contracts import RECORD_SCHEMA_VERSION, v2_block_from_payload
from profit_accounting_26.application.history_record_service import HistoryRecordV2Service
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.application.record_service import RecordService
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore
from profit_accounting_26.storage.image_store import ImageStore


def make_paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )


@pytest.fixture()
def bridge(tmp_path: Path):
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    image_store = ImageStore(store, paths.data_dir)
    image_store.initialize()
    history_service = HistoryRecordV2Service(store)
    service = RecordService(store, paths, image_store=image_store, history_service=history_service)
    return paths, store, image_store, history_service, service


def _payload(name: str, *, selected: str = "正常档") -> dict:
    return {
        "product_name": name,
        "layers": {
            "adopted": {
                "selected_packaging": selected,
                "normal": {
                    "packaging_method": "袋装", "length_cm": 11, "width_cm": 9,
                    "height_cm": 2, "weight_g": 60,
                },
                "conservative": {
                    "packaging_method": "盒装", "length_cm": 12, "width_cm": 10,
                    "height_cm": 3, "weight_g": 70,
                },
            }
        },
    }


def _image(tmp_path: Path, name: str = "a.png", data: bytes = b"img-bytes") -> SessionImage:
    source = tmp_path / name
    source.write_bytes(data)
    return SessionImage(source, ImageType.MAIN, hashlib.sha256(data).hexdigest(), source.name)


def test_new_record_save_revision_1(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    record_id = service.save(_payload("新品"), images=[])
    block = v2_block_from_payload(service.load(record_id))
    assert block["revision"] == 1
    assert block["origin"] == "new_calculation"
    assert block["record_schema_version"] == RECORD_SCHEMA_VERSION


def test_restore_resave_same_id_revision_2(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    first_id = service.save(_payload("商品"), images=[])
    second_id = service.save(_payload("商品修改"), images=[], record_id=first_id)
    assert second_id == first_id
    block = v2_block_from_payload(service.load(first_id))
    assert block["revision"] == 2
    assert block["origin"] == "history_edit"


def test_third_save_revision_3_same_id(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    record_id = service.save(_payload("商品"), images=[])
    service.save(_payload("商品修改1"), images=[], record_id=record_id)
    service.save(_payload("商品修改2"), images=[], record_id=record_id)
    block = v2_block_from_payload(service.load(record_id))
    assert block["revision"] == 3
    assert block["origin"] == "history_edit"


def test_ai_initial_kept_on_history_update(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    ai_initial = {"model": "m1", "prompt_version": "pv1", "observation": {"length_cm": 10}}
    record_id = service.save(_payload("商品"), images=[], ai_initial=ai_initial)
    # 历史恢复后再保存：不传新 ai_initial，由 V2Service 保留首次值
    service.save(_payload("商品修改"), images=[], record_id=record_id)
    block = v2_block_from_payload(service.load(record_id))
    assert block["ai_initial"] == ai_initial
    assert block["revision"] == 2


def test_current_estimate_from_adopted_tier(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    normal_id = service.save(_payload("正常档商品"), images=[])
    normal_estimate = v2_block_from_payload(service.load(normal_id))["current_estimate"]
    assert normal_estimate["packaging_method"] == "袋装"
    assert normal_estimate["length_cm"] == 11
    assert normal_estimate["selected_packaging"] == "正常档"

    conservative_id = service.save(_payload("保守档商品", selected="保守档"), images=[])
    conservative_estimate = v2_block_from_payload(service.load(conservative_id))["current_estimate"]
    assert conservative_estimate["packaging_method"] == "盒装"
    assert conservative_estimate["length_cm"] == 12
    assert conservative_estimate["selected_packaging"] == "保守档"


def test_image_store_dedup_same_bytes(bridge, tmp_path):
    _paths, store, image_store, _history_service, service = bridge
    image = _image(tmp_path)
    service.save(_payload("A"), images=[image])
    service.save(_payload("B"), images=[image])
    assert len(image_store.list_all()) == 1
    assert len(store.list_records()) == 2


def test_record_images_have_new_refs_and_compat_fields(bridge, tmp_path):
    paths, _store, _image_store, _history_service, service = bridge
    image = _image(tmp_path)
    record_id = service.save(_payload("A"), images=[image])
    entry = service.load(record_id)["images"][0]
    # ImageStore 新引用
    assert entry["image_id"]
    assert entry["image_hash"] == image.sha256
    assert entry["storage_key"].startswith("images/originals/")
    assert entry["original_filename"] == "a.png"
    # 兼容字段
    assert entry["relative_path"] == entry["storage_key"]
    assert entry["image_type"] == ImageType.MAIN.value
    assert entry["order"] == 0
    assert entry["original_name"] == "a.png"
    assert entry["sha256"] == entry["image_hash"]
    assert (paths.data_dir / entry["relative_path"]).is_file()


def test_images_reload_after_save(bridge, tmp_path):
    paths, _store, _image_store, _history_service, service = bridge
    image = _image(tmp_path)
    record_id = service.save(_payload("A"), images=[image])
    entry = service.load(record_id)["images"][0]
    original = paths.data_dir / entry["relative_path"]
    assert original.is_file()
    assert original.read_bytes() == b"img-bytes"
    thumbnail = entry["thumbnail_key"]
    assert thumbnail is None or (paths.data_dir / thumbnail).is_file()


def test_legacy_record_without_v2_gains_v2_same_id(bridge):
    _paths, store, _image_store, _history_service, service = bridge
    legacy_id = store.save_new_record({"product_name": "旧记录", "images": []})
    assert "_v2" not in store.load_record(legacy_id)
    saved_id = service.save(_payload("旧记录修改"), images=[], record_id=legacy_id)
    assert saved_id == legacy_id
    block = v2_block_from_payload(service.load(legacy_id))
    assert block["record_schema_version"] == RECORD_SCHEMA_VERSION
    assert block["origin"] == "history_edit"
    assert block["revision"] >= 1


def test_snapshots_preserved_through_bridge(bridge):
    _paths, _store, _image_store, _history_service, service = bridge
    record_id = service.save(_payload("商品"), images=[])
    service.save(_payload("商品修改"), images=[], record_id=record_id)
    kinds = [item["kind"] for item in service.snapshots(record_id)]
    assert kinds == ["initial", "recalculation"]
