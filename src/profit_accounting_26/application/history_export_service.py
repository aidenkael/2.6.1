"""Full History Export V1 / Calibration Feedback Export V1 后端导出器。

职责边界：只处理导出。不做 UI 按钮、不上传服务器、不修改记录内容。

格式：
- ``history-export-v1.zip``        manifest.json + records.json + feedback.json
- ``calibration-feedback-v1.zip``  manifest.json + feedback.json + records_summary.json
  （明确需要图片时才含 images/；默认只保留图片 hash/metadata）

安全：
- 导出内容递归脱敏（API key / Authorization / Bearer / data URL / 绝对路径）；
  脱敏后仍检测到敏感模式则中止导出。
- ZIP 内一律使用我们生成的相对文件名，不存在路径穿越与绝对路径泄露。
- 图片 storage key 为相对路径；默认不把高清原图复制进导出包。

防重复导出：只提供状态（calibration_exported_at / batch_id /
feedback_updated_after_export），不阻止用户再次导出。
"""

from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.storage.sqlite_store import SQLiteStore

FULL_EXPORT_FORMAT = "history-export-v1"
CALIBRATION_EXPORT_FORMAT = "calibration-feedback-v1"
SOFTWARE_VERSION = "2.6.1"

_FORBIDDEN_KEY_NAMES = {
    "api_key", "apikey", "api-key", "authorization", "auth", "token", "access_token",
    "secret", "secret_key", "password", "credential", "credentials", "bearer",
    "private_key", "client_secret",
}
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _basename_for_export(text: str) -> str:
    """跨平台提取绝对路径的 basename，普通字符串原样返回。"""
    if re.fullmatch(r"[A-Za-z]:[\\/].*", text) or text.startswith("\\\\"):
        # Windows 风格绝对路径 / UNC：无论运行平台都按 Windows 分隔符解析
        return PureWindowsPath(text).name
    if text.startswith("/"):
        return PurePosixPath(text).name
    return text


def sanitize_for_export(value: Any) -> Any:
    """递归脱敏：剥离敏感键、替换 data URL、去除路径中的目录信息。"""
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEY_NAMES:
                continue
            output[key] = sanitize_for_export(item)
        return output
    if isinstance(value, list):
        return [sanitize_for_export(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if text.lower().startswith("data:image"):
            return "[image base64 omitted]"
        if re.fullmatch(r"[A-Za-z]:[\\/].*", text) or text.startswith(("/", "\\\\")):
            return _basename_for_export(text)  # 绝对路径只保留文件名
        return value
    return value


def scan_export_text(text: str) -> list[str]:
    findings = []
    for pattern in _SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.append(pattern.pattern)
    return findings


def _distinct_nonempty(values: Any) -> str | list[str] | None:
    """去重排序非空字符串：单个返回字符串，多个返回列表，全空返回 None。"""
    seen = sorted({value for value in values if value})
    if not seen:
        return None
    return seen[0] if len(seen) == 1 else seen


def _record_model(record: dict[str, Any]) -> str | None:
    """从记录实际 AI raw 中读取模型：兼容顶层 model 与 observation.model 两种落位。"""
    layers = record.get("layers") if isinstance(record.get("layers"), dict) else {}
    ai_raw = layers.get("ai_raw") if isinstance(layers.get("ai_raw"), dict) else {}
    model = ai_raw.get("model")
    if not model:
        observation = ai_raw.get("observation") if isinstance(ai_raw.get("observation"), dict) else {}
        model = observation.get("model")
    if not model:
        return None
    return str(model).strip() or None


def _record_rule_version(record: dict[str, Any]) -> str | None:
    """从记录实际计算快照中读取规则/引擎版本（packaging_engine_version）。"""
    layers = record.get("layers") if isinstance(record.get("layers"), dict) else {}
    calculated = layers.get("calculated") if isinstance(layers.get("calculated"), dict) else {}
    version = calculated.get("packaging_engine_version")
    if not version:
        return None
    return str(version).strip() or None


def _export_model(records: list[dict[str, Any]]) -> str | list[str] | None:
    """导出批次实际可获得的模型集合：单一模型返回字符串，多个返回列表，无法获得返回 None。"""
    return _distinct_nonempty(_record_model(record) for record in records)


def _export_rule_version(records: list[dict[str, Any]]) -> str | list[str] | None:
    """导出批次实际可获得的规则/引擎版本集合，无法获得返回 None，不伪造。"""
    return _distinct_nonempty(_record_rule_version(record) for record in records)


class ExportAbortError(RuntimeError):
    """脱敏后仍检测到敏感内容时中止导出。"""


class HistoryExportService:
    def __init__(
        self,
        store: SQLiteStore,
        feedback_service: CalibrationFeedbackService,
        data_dir: str | Path | None = None,
    ) -> None:
        self.store = store
        self.feedback = feedback_service
        self.data_dir = Path(data_dir) if data_dir else None

    # ------------------------------------------------------------ selection

    def select_records(
        self,
        *,
        mode: str = "all",
        record_ids: list[str] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        updated_after: str | None = None,
        updated_before: str | None = None,
        unexported_calibration_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Export range：all / record_ids / created_at 区间 / updated_at 区间 /
        unexported_calibration_only。不实现复杂搜索 DSL。"""
        records = self.store.export_records()
        if mode == "record_ids":
            wanted = set(record_ids or [])
            records = [record for record in records if record.get("id") in wanted]
        elif mode == "created_at_range":
            records = [
                record for record in records
                if _in_range(record.get("_created_at"), created_after, created_before)
            ]
        elif mode == "updated_at_range":
            records = [
                record for record in records
                if _in_range(record.get("_updated_at"), updated_after, updated_before)
            ]
        elif mode != "all":
            raise ValueError(f"未知导出范围: {mode}")
        if unexported_calibration_only:
            unexported_record_ids = {
                item.record_id
                for item in self.feedback.list_all()
                if not item.calibration_exported_at or item.feedback_updated_after_export
            }
            records = [record for record in records if record.get("id") in unexported_record_ids]
        return records

    # ------------------------------------------------------------ full export

    def export_full(
        self,
        target: str | Path,
        *,
        mode: str = "all",
        include_images: bool = False,
        **selection: Any,
    ) -> Path:
        records = self.select_records(mode=mode, **selection)
        sanitized_records = [sanitize_for_export(record) for record in records]
        record_ids = [str(record.get("id") or "") for record in sanitized_records]
        feedback_items = [
            item.to_dict()
            for record_id in record_ids
            for item in self.feedback.for_record(record_id)
        ]
        feedback_items = sanitize_for_export(feedback_items)
        manifest = self._build_manifest(
            FULL_EXPORT_FORMAT,
            record_count=len(sanitized_records),
            feedback_count=len(feedback_items),
            include_images=include_images,
            image_entries=self._image_metadata(sanitized_records),
            records=records,
        )
        image_files = self._collect_image_files(sanitized_records) if include_images else []
        return self._write_zip(target, manifest, {
            "records.json": {"format": FULL_EXPORT_FORMAT, "records": sanitized_records},
            "feedback.json": {"format": CALIBRATION_EXPORT_FORMAT, "items": feedback_items},
        }, image_files)

    # ------------------------------------------------------------ calibration export

    def export_calibration(
        self,
        target: str | Path,
        *,
        mode: str = "all",
        include_images: bool = False,
        mark_exported: bool = True,
        **selection: Any,
    ) -> Path:
        records = self.select_records(mode=mode, **selection)
        record_index = {str(record.get("id") or ""): record for record in records}
        feedback_items: list[dict[str, Any]] = []
        for record_id, record in record_index.items():
            for item in self.feedback.for_record(record_id):
                feedback_items.append(item.to_dict())
        if mode == "all" and not selection and not record_index:
            # 没有任何记录时仍允许导出全部反馈（开发者反馈包场景）
            feedback_items = [item.to_dict() for item in self.feedback.list_all()]
        feedback_items = sanitize_for_export(feedback_items)
        summaries = sanitize_for_export([
            self._record_summary(record_index.get(item.get("record_id") or "", {}), item)
            for item in feedback_items
        ])
        batch_id = f"cal-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        manifest = self._build_manifest(
            CALIBRATION_EXPORT_FORMAT,
            record_count=len(record_index),
            feedback_count=len(feedback_items),
            include_images=include_images,
            image_entries=self._image_metadata(list(record_index.values())),
            batch_id=batch_id,
            records=records,
        )
        image_files = (
            self._collect_image_files(list(record_index.values())) if include_images else []
        )
        path = self._write_zip(target, manifest, {
            "feedback.json": {"format": CALIBRATION_EXPORT_FORMAT, "batch_id": batch_id,
                               "items": feedback_items},
            "records_summary.json": {"format": CALIBRATION_EXPORT_FORMAT, "summaries": summaries},
        }, image_files)
        if mark_exported and feedback_items:
            self.feedback.mark_exported(
                [str(item.get("feedback_id") or "") for item in feedback_items if item.get("feedback_id")],
                batch_id=batch_id,
            )
        return path

    # ------------------------------------------------------------ helpers

    def _build_manifest(
        self,
        export_format: str,
        *,
        record_count: int,
        feedback_count: int,
        include_images: bool,
        image_entries: list[dict[str, Any]],
        batch_id: str | None = None,
        records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from profit_accounting_26.application.recognition_service import RecognitionService

        return {
            "format": export_format,
            "batch_id": batch_id or f"exp-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}",
            "exported_at": datetime.now(UTC).isoformat(),
            "software_version": SOFTWARE_VERSION,
            "prompt_version": RecognitionService.PROMPT_VERSION,
            "model": _export_model(records or []),
            "rule_version": _export_rule_version(records or []),
            "record_count": record_count,
            "feedback_count": feedback_count,
            "include_images": include_images,
            "images": image_entries,
            "note": "导出内容已脱敏；图片默认只含 hash/metadata，不含二进制。",
        }

    @staticmethod
    def _image_metadata(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            images = record.get("images")
            if not isinstance(images, list):
                continue
            for item in images:
                if not isinstance(item, dict):
                    continue
                digest = str(item.get("sha256") or item.get("image_hash") or "")
                key = digest or str(item.get("storage_key") or item.get("relative_path") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                entries.append({
                    "sha256": digest or None,
                    "storage_key": item.get("storage_key") or item.get("relative_path"),
                    "original_filename": item.get("original_filename") or item.get("original_name"),
                    "image_type": item.get("image_type"),
                })
        return entries

    def _collect_image_files(self, records: list[dict[str, Any]]) -> list[tuple[Path, str]]:
        """include_images=true 时复制原图进包；文件缺失安全跳过。"""
        if self.data_dir is None:
            return []
        files: list[tuple[Path, str]] = []
        seen: set[str] = set()
        for record in records:
            images = record.get("images")
            if not isinstance(images, list):
                continue
            for item in images:
                if not isinstance(item, dict):
                    continue
                relative = str(item.get("storage_key") or item.get("relative_path") or "")
                if not relative or relative in seen:
                    continue
                seen.add(relative)
                source = (self.data_dir / relative).resolve()
                # 防路径穿越：只允许 data_dir 内的文件
                if not source.is_file() or self.data_dir.resolve() not in source.parents:
                    continue
                arcname = "images/" + Path(relative).name
                files.append((source, arcname))
        return files

    @staticmethod
    def _record_summary(record: dict[str, Any], feedback: dict[str, Any]) -> dict[str, Any]:
        layers = record.get("layers") if isinstance(record.get("layers"), dict) else {}
        v2 = record.get("_v2") if isinstance(record.get("_v2"), dict) else {}
        return {
            "record_id": record.get("id") or feedback.get("record_id"),
            "product_name": record.get("product_name"),
            "product_link": record.get("product_link"),
            "bare_facts": layers.get("adopted", {}).get("bare", {}) if isinstance(layers.get("adopted"), dict) else {},
            "ai_initial": v2.get("ai_initial") or layers.get("ai_raw"),
            "current_estimate": v2.get("current_estimate") or {},
            "legacy_packaging_output": {
                "normal": layers.get("adopted", {}).get("normal") if isinstance(layers.get("adopted"), dict) else None,
                "conservative": layers.get("adopted", {}).get("conservative") if isinstance(layers.get("adopted"), dict) else None,
            },
            "model": (layers.get("ai_raw") or {}).get("model") if isinstance(layers.get("ai_raw"), dict) else None,
            "engine_versions": layers.get("calculated", {}) if isinstance(layers.get("calculated"), dict) else {},
            "image_hashes": [
                item.get("sha256") or item.get("image_hash")
                for item in (record.get("images") or [])
                if isinstance(item, dict)
            ],
        }

    def _write_zip(
        self,
        target: str | Path,
        manifest: dict[str, Any],
        payloads: dict[str, Any],
        image_files: list[tuple[Path, str]],
    ) -> Path:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
        texts = {"manifest.json": manifest_text}
        texts.update({
            name: json.dumps(payload, ensure_ascii=False, indent=2)
            for name, payload in payloads.items()
        })
        for name, text in texts.items():
            findings = scan_export_text(text)
            if findings:
                raise ExportAbortError(f"导出中止：{name} 脱敏后仍检测到敏感内容: {', '.join(findings)}")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, text in texts.items():
                _assert_safe_arcname(name)
                bundle.writestr(name, text)
            for source, arcname in image_files:
                _assert_safe_arcname(arcname)
                bundle.write(source, arcname)
        return path


def _in_range(value: Any, after: str | None, before: str | None) -> bool:
    text = str(value or "")
    if not text:
        return False
    if after and text < after:
        return False
    if before and text > before:
        return False
    return True


def _assert_safe_arcname(name: str) -> None:
    """ZIP 路径穿越防护：只允许相对路径、无 .. 、无盘符/根。"""
    if not name or name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name:
        raise ExportAbortError(f"导出中止：非法 ZIP 条目名 {name!r}")
