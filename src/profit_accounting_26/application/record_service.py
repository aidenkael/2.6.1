from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


class RecordService:
    def __init__(self, store: SQLiteStore, paths: ApplicationPaths) -> None:
        self.store = store
        self.paths = paths

    def _persist_images(self, record_id: str, images: list[SessionImage]) -> list[dict[str, Any]]:
        record_dir = self.paths.images_dir / record_id
        record_dir.mkdir(parents=True, exist_ok=True)
        output: list[dict[str, Any]] = []
        for index, image in enumerate(images):
            suffix = image.path.suffix.lower() or ".png"
            target_name = f"{index + 1:02d}_{image.sha256[:12]}{suffix}"
            target = record_dir / target_name
            if not target.exists():
                shutil.copy2(image.path, target)
            output.append(
                {
                    "relative_path": target.relative_to(self.paths.data_dir).as_posix(),
                    "image_type": image.image_type.value,
                    "order": index,
                    "original_name": image.original_name,
                    "sha256": image.sha256,
                }
            )
        return output

    def save(
        self,
        payload: dict[str, Any],
        *,
        images: list[SessionImage],
        record_id: str | None = None,
    ) -> str:
        identifier = record_id or str(payload.get("id") or uuid4())
        now = datetime.now(UTC).isoformat()
        image_payload = self._persist_images(identifier, images)
        final_payload = {
            **payload,
            "id": identifier,
            "images": image_payload,
            "updated_at": now,
        }
        if record_id is None:
            final_payload.setdefault("created_at", now)
            self.store.save_new_record(final_payload)
        else:
            existing = self.store.load_record(identifier)
            final_payload.setdefault("created_at", existing.get("created_at", now))
            self.store.update_record(identifier, final_payload)
        return identifier

    def list(self, *, search: str = "") -> list[dict[str, Any]]:
        return self.store.list_records(search=search)

    def load(self, record_id: str) -> dict[str, Any]:
        return self.store.load_record(record_id)

    def snapshots(self, record_id: str) -> list[dict[str, Any]]:
        return self.store.list_snapshots(record_id)
