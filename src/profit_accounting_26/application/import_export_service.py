from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from profit_accounting_26.storage import SQLiteStore


class ImportExportService:
    FORMAT_VERSION = "profit-accounting-2.6-export-v1"

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def export_records(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": self.FORMAT_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "records": self.store.export_records(),
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def import_records(self, path: str | Path, *, overwrite: bool = False) -> dict[str, Any]:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("format") != self.FORMAT_VERSION:
            raise ValueError("不支持的导入格式")
        created = updated = conflicts = 0
        conflict_ids: list[str] = []
        for record in payload.get("records", []):
            if not isinstance(record, dict):
                continue
            record_id = str(record.get("id") or "")
            existed = bool(record_id and self.store.record_exists(record_id))
            try:
                self.store.upsert_imported_record(record, overwrite=overwrite)
                if existed:
                    updated += 1
                else:
                    created += 1
            except FileExistsError:
                conflicts += 1
                conflict_ids.append(str(record.get("id") or ""))
        return {
            "created": created,
            "updated": updated,
            "conflicts": conflicts,
            "conflict_ids": conflict_ids,
        }

    def export_calibration_feedback(self, path: str | Path) -> Path:
        records = self.store.export_records()
        feedback = []
        for record in records:
            actual = record.get("layers", {}).get("actual", {})
            calculated = record.get("layers", {}).get("calculated", {})
            if actual:
                feedback.append(
                    {
                        "record_id": record.get("id"),
                        "product_name": record.get("product_name", ""),
                        "ai_raw": record.get("layers", {}).get("ai_raw", {}),
                        "adopted": record.get("layers", {}).get("adopted", {}),
                        "calculated": calculated,
                        "actual": actual,
                    }
                )
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "format": "profit-accounting-2.6-calibration-feedback-v1",
                    "exported_at": datetime.now(UTC).isoformat(),
                    "items": feedback,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return target
