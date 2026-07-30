import sqlite3
from pathlib import Path

import pytest

from profit_accounting_26.storage import SQLiteStore


def test_initialize_save_and_initial_snapshot(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    record_id = store.save_new_record({"name": "sample", "layers": {"ai_raw": {}, "adopted": {}}})
    assert store.load_record(record_id)["name"] == "sample"
    with sqlite3.connect(store.path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM snapshots WHERE record_id = ? AND kind = 'initial'", (record_id,)
        ).fetchone()[0]
    assert count == 1


def test_update_preserves_initial_and_adds_recalculation(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    record_id = store.save_new_record({"value": 1})
    store.update_record(record_id, {"value": 2})
    assert store.load_record(record_id)["value"] == 2
    with sqlite3.connect(store.path) as connection:
        kinds = [row[0] for row in connection.execute(
            "SELECT kind FROM snapshots WHERE record_id = ? ORDER BY created_at", (record_id,)
        )]
    assert kinds.count("initial") == 1
    assert "recalculation" in kinds


def test_update_unknown_record_rolls_back(tmp_path: Path):
    store = SQLiteStore(tmp_path / "app.sqlite3")
    store.initialize()
    with pytest.raises(KeyError):
        store.update_record("missing", {"value": 2})
