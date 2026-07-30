from __future__ import annotations

import json
from pathlib import Path

import pytest

from profit_accounting_26.application import ImportExportService, RecordService
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.domain.models import ImageType
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


def make_paths(tmp_path: Path) -> ApplicationPaths:
    return ApplicationPaths(
        data_dir=tmp_path,
        database_path=tmp_path / "app.sqlite3",
        settings_path=tmp_path / "settings.json",
        images_dir=tmp_path / "images",
        exports_dir=tmp_path / "exports",
        calibration_packages_dir=tmp_path / "calibration_packages",
    )


def test_record_service_persists_image_without_moving_source(tmp_path: Path):
    paths = make_paths(tmp_path / "data")
    paths.ensure()
    store = SQLiteStore(paths.database_path)
    store.initialize()
    source = tmp_path / "source.png"
    source.write_bytes(b"image")
    image = SessionImage(source, ImageType.MAIN, "a" * 64, source.name)
    service = RecordService(store, paths)
    record_id = service.save({"product_name": "sample"}, images=[image])
    record = service.load(record_id)
    assert source.exists()
    saved = paths.data_dir / record["images"][0]["relative_path"]
    assert saved.exists()
    assert record["images"][0]["original_name"] == "source.png"


def test_import_conflict_is_not_silently_overwritten(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    record_id = store.save_new_record({"product_name": "original"})
    service = ImportExportService(store)
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "format": service.FORMAT_VERSION,
                "records": [{"id": record_id, "product_name": "changed"}],
            }
        ),
        encoding="utf-8",
    )
    result = service.import_records(source, overwrite=False)
    assert result["conflicts"] == 1
    assert store.load_record(record_id)["product_name"] == "original"


def test_import_can_overwrite_only_when_explicit(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    record_id = store.save_new_record({"product_name": "original"})
    service = ImportExportService(store)
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "format": service.FORMAT_VERSION,
                "records": [{"id": record_id, "product_name": "changed"}],
            }
        ),
        encoding="utf-8",
    )
    result = service.import_records(source, overwrite=True)
    assert result["updated"] == 1
    assert store.load_record(record_id)["product_name"] == "changed"


def test_import_overwrite_counts_new_and_existing_separately(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    existing_id = store.save_new_record({"product_name": "original"})
    service = ImportExportService(store)
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps(
            {
                "format": service.FORMAT_VERSION,
                "records": [
                    {"id": existing_id, "product_name": "updated"},
                    {"id": "new-record", "product_name": "new"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = service.import_records(source, overwrite=True)
    assert result == {
        "created": 1,
        "updated": 1,
        "conflicts": 0,
        "conflict_ids": [],
    }
