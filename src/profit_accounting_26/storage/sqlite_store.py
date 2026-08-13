from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(record_id) REFERENCES records(id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calibration_packages (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    path TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    imported_at TEXT NOT NULL
);
"""


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def save_new_record(self, payload: dict[str, Any]) -> str:
        record_id = str(payload.get("id") or uuid4())
        now = datetime.now(UTC).isoformat()
        serialized = self._serialize({**payload, "id": record_id})
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO records(id, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (record_id, serialized, now, now),
            )
            connection.execute(
                "INSERT INTO snapshots(id, record_id, kind, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), record_id, "initial", serialized, now),
            )
        return record_id

    def update_record(self, record_id: str, payload: dict[str, Any], *, snapshot_kind: str = "recalculation") -> None:
        now = datetime.now(UTC).isoformat()
        serialized = self._serialize({**payload, "id": record_id})
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE records SET payload_json = ?, updated_at = ? WHERE id = ?",
                (serialized, now, record_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(record_id)
            connection.execute(
                "INSERT INTO snapshots(id, record_id, kind, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), record_id, snapshot_kind, serialized, now),
            )

    def load_record(self, record_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM records WHERE id = ?", (record_id,)
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row["payload_json"])

    def list_records(self, *, search: str = "", limit: int = 500) -> list[dict[str, Any]]:
        query = "SELECT id, payload_json, created_at, updated_at FROM records ORDER BY updated_at DESC LIMIT ?"
        with self.connect() as connection:
            rows = connection.execute(query, (limit,)).fetchall()
        needle = search.strip().lower()
        output: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload.setdefault("id", row["id"])
            payload["_created_at"] = row["created_at"]
            payload["_updated_at"] = row["updated_at"]
            if needle:
                haystack = json.dumps(payload, ensure_ascii=False).lower()
                if needle not in haystack:
                    continue
            output.append(payload)
        return output

    def list_snapshots(self, record_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, kind, payload_json, created_at FROM snapshots WHERE record_id = ? ORDER BY created_at",
                (record_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_record(self, record_id: str) -> None:
        """永久删除记录及其全部快照（snapshots 外键无 CASCADE，需先删）。"""
        with self.connect() as connection:
            connection.execute("DELETE FROM snapshots WHERE record_id = ?", (record_id,))
            cursor = connection.execute("DELETE FROM records WHERE id = ?", (record_id,))
            if cursor.rowcount != 1:
                raise KeyError(record_id)

    def set_setting(self, key: str, value: Any) -> None:
        now = datetime.now(UTC).isoformat()
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (key, serialized, now),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return default if row is None else json.loads(row["value_json"])

    def export_records(self) -> list[dict[str, Any]]:
        return self.list_records(limit=100000)

    def record_exists(self, record_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM records WHERE id = ?", (record_id,)
            ).fetchone()
        return row is not None

    def register_calibration_package(
        self,
        *,
        version: str,
        path: str,
        metadata: dict[str, Any],
        activate: bool = True,
    ) -> str:
        package_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            if activate:
                connection.execute("UPDATE calibration_packages SET active = 0")
            connection.execute(
                "INSERT INTO calibration_packages(id, version, path, metadata_json, active, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    package_id,
                    version,
                    path,
                    self._serialize(metadata),
                    int(activate),
                    now,
                ),
            )
        return package_id

    def list_calibration_packages(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM calibration_packages ORDER BY imported_at DESC"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "version": row["version"],
                "path": row["path"],
                "metadata": json.loads(row["metadata_json"]),
                "active": bool(row["active"]),
                "imported_at": row["imported_at"],
            }
            for row in rows
        ]

    def update_calibration_package_metadata(
        self, package_id: str, metadata: dict[str, Any]
    ) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE calibration_packages SET metadata_json = ? WHERE id = ?",
                (self._serialize(metadata), package_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(package_id)

    def get_active_calibration(self) -> dict[str, Any] | None:
        return next(
            (item for item in self.list_calibration_packages() if item["active"]),
            None,
        )

    def activate_calibration(self, package_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM calibration_packages WHERE id = ?", (package_id,)
            ).fetchone()
            if row is None:
                raise KeyError(package_id)
            connection.execute("UPDATE calibration_packages SET active = 0")
            connection.execute(
                "UPDATE calibration_packages SET active = 1 WHERE id = ?", (package_id,)
            )
        active = self.get_active_calibration()
        if active is None:
            raise RuntimeError("校准包激活失败")
        return active

    def delete_calibration_package(self, package_id: str) -> None:
        """删除校准包注册记录（不删除文件，文件由 Manager 层在切换成功后清理）。"""
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM calibration_packages WHERE id = ?", (package_id,)
            )
            if cursor.rowcount == 0:
                raise KeyError(package_id)
