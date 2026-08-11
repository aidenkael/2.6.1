from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


class CalibrationManager:
    """Import, activate and safely delete data-only packaging calibration packages."""

    MAX_JSON_BYTES = 20 * 1024 * 1024

    def __init__(self, store: SQLiteStore, paths: ApplicationPaths) -> None:
        self.store = store
        self.paths = paths
        self._service: PackagingEstimationService | None = None

    def bind_service(self, service: PackagingEstimationService) -> None:
        self._service = service

    @staticmethod
    def _validate_payload(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
        declared_version: str | None = None
        if isinstance(payload, dict):
            declared_version = str(
                payload.get("version") or payload.get("calibration_version") or ""
            ).strip() or None
            payload = payload.get("samples") or payload.get("items")
        if not isinstance(payload, list):
            raise ValueError("校准JSON必须是样本列表，或包含 samples/items 列表")
        samples = [item for item in payload if isinstance(item, dict)]
        if not samples:
            raise ValueError("校准数据不包含有效样本")
        return samples, declared_version

    @classmethod
    def _read_json_payload(cls, path: Path) -> tuple[list[dict[str, Any]], str | None]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"无法读取校准JSON：{exc}") from exc
        return cls._validate_payload(payload)

    @classmethod
    def _read_zip_payload(
        cls,
        path: Path,
    ) -> tuple[list[dict[str, Any]], str | None, str]:
        try:
            with zipfile.ZipFile(path) as archive:
                candidates: list[str] = []
                for info in archive.infolist():
                    name = info.filename
                    pure = PurePosixPath(name)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise ValueError("校准ZIP包含不安全路径")
                    if info.file_size > cls.MAX_JSON_BYTES and pure.suffix.lower() == ".json":
                        continue
                    if pure.suffix.lower() == ".json" and not name.endswith("/"):
                        candidates.append(name)
                if not candidates:
                    raise ValueError("校准ZIP中没有JSON数据文件")
                candidates.sort(
                    key=lambda name: (
                        0 if "calibration" in name.lower() else 1,
                        len(PurePosixPath(name).parts),
                        name,
                    )
                )
                errors: list[str] = []
                for name in candidates:
                    try:
                        raw = archive.read(name)
                        payload = json.loads(raw.decode("utf-8"))
                        samples, version = cls._validate_payload(payload)
                        return samples, version, name
                    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                        errors.append(f"{name}: {exc}")
                raise ValueError("ZIP中的JSON均不是有效校准数据：" + "；".join(errors[:3]))
        except zipfile.BadZipFile as exc:
            raise ValueError("校准ZIP损坏") from exc

    def _activate_service(self, package: dict[str, Any]) -> None:
        if self._service is not None:
            self._service.activate(package["path"], version=str(package["version"]))

    def _safe_runtime_activate(
        self,
        new_package: dict[str, Any],
        previous_active: dict[str, Any] | None,
    ) -> None:
        """激活运行时服务，失败时补偿恢复 DB 和 runtime 到切换前状态。

        只有最终状态核对确认 DB 与 runtime 都已恢复时才报告“已恢复”；
        补偿恢复本身失败时抛严重错误，不吞异常、不声称已恢复。
        """
        original_error: Exception | None = None
        try:
            self._activate_service(new_package)
            return
        except Exception as exc:
            original_error = exc

        if previous_active is None:
            raise RuntimeError(
                f"运行时激活失败且没有切换前版本可恢复：{original_error}"
            ) from original_error

        recovery_errors: list[str] = []
        try:
            self.store.activate_calibration(previous_active["id"])
        except Exception as restore_error:
            recovery_errors.append(f"DB 恢复失败: {restore_error}")
        try:
            self._activate_service(previous_active)
        except Exception as restore_error:
            recovery_errors.append(f"运行时恢复失败: {restore_error}")

        # 最终状态核对：只有实际核对通过才允许声称“已恢复”
        db_active = self.store.get_active_calibration()
        if db_active is None or db_active["id"] != previous_active["id"]:
            recovery_errors.append("最终核对：DB active 不是切换前版本")
        if self._service is not None:
            runtime_ok = (
                str(self._service.calibration_version) == str(previous_active["version"])
                and Path(self._service.calibration_path) == Path(previous_active["path"])
            )
            if not runtime_ok:
                recovery_errors.append("最终核对：运行时服务不是切换前版本")

        if recovery_errors:
            raise RuntimeError(
                "运行时激活失败且补偿恢复也失败，当前校准状态需要重新校验。"
                f"原始错误：{original_error}；恢复问题：{'；'.join(recovery_errors)}"
            ) from original_error
        raise RuntimeError(
            f"运行时激活失败，已恢复到切换前状态：{original_error}"
        ) from original_error

    def ensure_builtin(self, source: str | Path, *, version: str) -> dict[str, Any]:
        source_path = Path(source)
        samples, _ = self._read_json_payload(source_path)
        packages = self.store.list_calibration_packages()
        existing = next(
            (
                item
                for item in packages
                if item.get("metadata", {}).get("builtin")
                and item.get("version") == version
            ),
            None,
        )
        if existing is None:
            target_dir = self.paths.calibration_packages_dir / "builtin"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "calibration.json"
            target.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            package_id = self.store.register_calibration_package(
                version=version,
                path=str(target),
                metadata={
                    "builtin": True,
                    "sample_count": len(samples),
                    "source": str(source_path),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                },
                activate=not packages,
            )
            existing = next(
                item
                for item in self.store.list_calibration_packages()
                if item["id"] == package_id
            )
        elif not Path(existing["path"]).is_file():
            target = Path(existing["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        active = self.store.get_active_calibration()
        active_valid = False
        if active is not None:
            try:
                self._read_json_payload(Path(active["path"]))
                active_valid = True
            except (OSError, ValueError):
                active_valid = False
        if not active_valid:
            active = self.store.activate_calibration(existing["id"])
        return active

    def import_package(self, source: str | Path) -> dict[str, Any]:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        package_dir = self.paths.calibration_packages_dir / f"{timestamp}_{digest[:10]}"
        package_dir.mkdir(parents=True, exist_ok=False)
        try:
            original_target = package_dir / path.name
            shutil.copy2(path, original_target)

            if path.suffix.lower() == ".json":
                if path.stat().st_size > self.MAX_JSON_BYTES:
                    raise ValueError("校准JSON超过20MB限制")
                samples, declared_version = self._read_json_payload(path)
                source_member = path.name
            elif path.suffix.lower() == ".zip":
                samples, declared_version, source_member = self._read_zip_payload(path)
            else:
                raise ValueError("只支持 .json 或 .zip 校准包")
        except Exception:
            shutil.rmtree(package_dir, ignore_errors=True)
            raise

        runtime_path = package_dir / "runtime_calibration.json"
        runtime_path.write_text(
            json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        version = declared_version or path.stem
        metadata = {
            "sha256": digest,
            "runtime_sha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
            "original_name": path.name,
            "source_member": source_member,
            "sample_count": len(samples),
            "imported_at": datetime.now(UTC).isoformat(),
            "declared_version": declared_version,
        }
        previous_active = self.active_package()
        package_id = self.store.register_calibration_package(
            version=version,
            path=str(runtime_path),
            metadata=metadata,
            activate=True,
        )
        active = next(
            item
            for item in self.store.list_calibration_packages()
            if item["id"] == package_id
        )
        try:
            self._safe_runtime_activate(active, previous_active)
        except RuntimeError as exc:
            db_active = self.store.get_active_calibration()
            if previous_active is None:
                recoverable = db_active is not None and db_active["id"] == active["id"]
            else:
                recoverable = db_active is not None and db_active["id"] == previous_active["id"]
            if not recoverable:
                raise RuntimeError(
                    f"导入失败且校准状态恢复失败，需要重新校验：{exc}"
                ) from exc
            # 恢复已确认成功：清理本次失败导入的注册记录与包目录，回到导入前状态
            try:
                self.store.delete_calibration_package(active["id"])
            except KeyError:
                pass
            self._remove_package_files(active)
            raise RuntimeError(f"导入失败，已恢复并清理：{exc}") from exc
        return active

    def list_packages(self) -> list[dict[str, Any]]:
        return self.store.list_calibration_packages()

    def active_package(self) -> dict[str, Any] | None:
        return self.store.get_active_calibration()

    def activate(self, package_id: str) -> dict[str, Any]:
        """启用任意已注册版本，并同步切换运行时包装估算服务。

        不存在的 package 由 store 抛 KeyError；运行时激活失败时
        DB 和 runtime 均恢复到切换前状态，保证一致性。
        """
        previous_active = self.active_package()
        active = self.store.activate_calibration(package_id)
        self._safe_runtime_activate(active, previous_active)
        return active

    def delete_package(self, package_id: str) -> dict[str, Any]:
        """删除指定校准包（注册记录 + 包目录文件）。

        - builtin 包禁止删除；
        - 删除当前启用版本时先 fallback 到 builtin（校验有效→切换→
          通知运行时→确认切换成功）后才删除原包；fallback 失败则不删除。
        返回删除后的 active package。
        """
        target = next(
            (item for item in self.store.list_calibration_packages() if item["id"] == package_id),
            None,
        )
        if target is None:
            raise KeyError(package_id)
        if target.get("metadata", {}).get("builtin"):
            raise ValueError("内置校准版本不允许删除")
        if target["active"]:
            previous_active = target
            fallback = self._prepare_builtin_fallback()
            active = self.store.activate_calibration(fallback["id"])
            try:
                self._safe_runtime_activate(active, previous_active)
            except RuntimeError as exc:
                db_active = self.store.get_active_calibration()
                if db_active is not None and db_active["id"] == previous_active["id"]:
                    raise RuntimeError(
                        f"切换到内置校准版本失败，已保留原启用版本：{exc}"
                    ) from exc
                raise RuntimeError(
                    f"切换到内置校准版本失败且恢复失败，当前校准状态需要重新校验：{exc}"
                ) from exc
        self.store.delete_calibration_package(package_id)
        self._remove_package_files(target)
        current = self.store.get_active_calibration()
        if current is None:
            raise RuntimeError("删除后数据库中没有有效启用版本")
        return current

    def _prepare_builtin_fallback(self) -> dict[str, Any]:
        """找到并校验 builtin 包；注册文件丢失时从原始源重写（与 ensure_builtin 同逻辑）。"""
        builtin = next(
            (
                item
                for item in self.store.list_calibration_packages()
                if item.get("metadata", {}).get("builtin")
            ),
            None,
        )
        if builtin is None:
            raise RuntimeError("没有可用的内置校准版本，无法删除当前启用版本")
        target = Path(builtin["path"])
        if not target.is_file():
            source = builtin.get("metadata", {}).get("source")
            if not source or not Path(source).is_file():
                raise RuntimeError("内置校准版本文件丢失且无法恢复，无法删除当前启用版本")
            samples, _ = self._read_json_payload(Path(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        try:
            self._read_json_payload(target)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"内置校准版本不可用，无法删除当前启用版本：{exc}") from exc
        return builtin

    def _remove_package_files(self, package: dict[str, Any]) -> None:
        """只允许删除正式校准包数据目录内的包目录，不根据任意外部路径递归删除。"""
        package_dir = Path(package["path"]).resolve().parent
        base_dir = self.paths.calibration_packages_dir.resolve()
        try:
            package_dir.relative_to(base_dir)
        except ValueError:
            return
        shutil.rmtree(package_dir, ignore_errors=True)
