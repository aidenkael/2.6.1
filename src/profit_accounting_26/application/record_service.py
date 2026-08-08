from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.application.history_record_service import HistoryRecordV2Service
from profit_accounting_26.application.image_session import SessionImage
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore
from profit_accounting_26.storage.image_store import ImageStore


class RecordService:
    def __init__(
        self,
        store: SQLiteStore,
        paths: ApplicationPaths,
        *,
        image_store: ImageStore | None = None,
        history_service: HistoryRecordV2Service | None = None,
        feedback_service: CalibrationFeedbackService | None = None,
    ) -> None:
        self.store = store
        self.paths = paths
        self.image_store = image_store
        self.history_service = history_service
        self.feedback_service = feedback_service

    def _persist_images(self, record_id: str, images: list[SessionImage]) -> list[dict[str, Any]]:
        if self.image_store is not None:
            return self._persist_images_via_image_store(images)
        return self._persist_images_legacy_copy(record_id, images)

    def _persist_images_via_image_store(self, images: list[SessionImage]) -> list[dict[str, Any]]:
        """内容寻址 ImageStore：原图去重入库，并保留旧恢复逻辑所需兼容字段。"""
        output: list[dict[str, Any]] = []
        for index, image in enumerate(images):
            reference = self.image_store.add_file(image.path, original_filename=image.original_name)
            output.append(
                {
                    # ImageStore 新引用字段
                    "image_id": reference.image_id,
                    "image_hash": reference.image_hash,
                    "storage_key": reference.storage_key,
                    "thumbnail_key": reference.thumbnail_key,
                    "original_filename": reference.original_filename,
                    # 兼容字段：current load_record_payload 恢复逻辑继续可用
                    "relative_path": reference.storage_key,
                    "image_type": image.image_type.value,
                    "order": index,
                    "original_name": image.original_name,
                    "sha256": reference.image_hash,
                }
            )
        return output

    def _persist_images_legacy_copy(self, record_id: str, images: list[SessionImage]) -> list[dict[str, Any]]:
        """旧复制路径：未注入 ImageStore 时保留原行为（兼容测试与回退）。"""
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
        ai_initial: dict[str, Any] | None = None,
        sku: str | None = None,
        quantity: int | None = None,
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
        if self.history_service is not None:
            return self.history_service.save(
                final_payload,
                ai_initial=ai_initial,
                current_estimate=_current_estimate_from_payload(final_payload),
                record_id=identifier,
                sku=sku,
                quantity=quantity,
            )
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

    def delete_record(self, record_id: str) -> None:
        """永久删除：记录 + 快照 + 绑定校准反馈 + 独占图片。

        内容寻址图片仅当无其他记录引用时才物理删除；
        legacy 图片位于 images/<record_id>/ 独占目录，直接删除。
        """
        payload = self.store.load_record(record_id)
        images = payload.get("images") if isinstance(payload.get("images"), list) else []
        if self.feedback_service is not None:
            self.feedback_service.delete_for_record(record_id)
        self.store.delete_record(record_id)
        legacy_dir = self.paths.images_dir / record_id
        for item in images:
            if not isinstance(item, dict):
                continue
            image_id = item.get("image_id")
            if image_id and self.image_store is not None:
                # 本记录已删；仍被引用则 delete_image 内部拒绝
                self.image_store.delete_image(str(image_id))
                continue
            relative = item.get("relative_path")
            if relative:
                target = self.paths.data_dir / str(relative)
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
        if legacy_dir.is_dir():
            shutil.rmtree(legacy_dir, ignore_errors=True)


def _current_estimate_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    """从当前真正被采用的包装档生成 V2 单一 current_estimate（不改旧 normal/conservative 结构）。"""
    layers = payload.get("layers") if isinstance(payload.get("layers"), dict) else {}
    adopted = layers.get("adopted") if isinstance(layers.get("adopted"), dict) else {}
    selected = str(adopted.get("selected_packaging") or "正常档")
    tier = adopted.get("conservative") if selected == "保守档" else adopted.get("normal")
    tier = tier if isinstance(tier, dict) else {}
    return {
        "packaging_method": tier.get("packaging_method"),
        "length_cm": tier.get("length_cm"),
        "width_cm": tier.get("width_cm"),
        "height_cm": tier.get("height_cm"),
        "weight_g": tier.get("weight_g"),
        "selected_packaging": selected,
    }
