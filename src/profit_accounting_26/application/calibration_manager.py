from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from profit_accounting_26.application.formal_bundle_importer import (
    FormalBundleValidationError,
    ValidatedFormalBundle,
    is_formal_bundle_zip,
    validate_formal_bundle_zip,
)
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.shared import ensure_data_dir_allowed, resource_path
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore

# CAL77 软件默认启动 registry
_CAL77_REGISTRY_PATH = resource_path("calibration/logistics_v2/packaging_rule_registry_v1.json")


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

    # ------------------------------------------------------------------
    # Registry path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expected_registry_path(package: dict[str, Any]) -> Path:
        """返回该 package 应使用的 registry 文件路径。

        - Formal Bundle: sibling packaging_rule_registry_v1.json
        - Legacy / builtin: CAL77 resource registry
        """
        if package.get("metadata", {}).get("formal_bundle"):
            return Path(package["path"]).with_name("packaging_rule_registry_v1.json")
        return _CAL77_REGISTRY_PATH

    def _activate_service(self, package: dict[str, Any]) -> None:
        """激活运行时服务并设置正确的 registry。

        1. service.activate(calibration_path, version)
        2. 将 service.rule_registry_path 设置为该 package 的预期 registry
        3. 从该 registry 重新加载 service.registry
        """
        if self._service is None:
            return
        self._service.activate(package["path"], version=str(package["version"]))
        expected_registry = self._expected_registry_path(package)
        self._service.rule_registry_path = expected_registry
        self._service.registry = self._service._load_registry(expected_registry)

    def _verify_runtime_package(self, package: dict[str, Any]) -> list[str]:
        """核对运行时服务的最终状态是否与 package 一致。

        返回错误列表；空列表表示核对通过。
        适用于：成功 activation、失败恢复、删除 fallback 后的核对。
        """
        errors: list[str] = []
        if self._service is None:
            return errors
        expected_cal_path = Path(package["path"])
        expected_version = str(package["version"])
        expected_registry = self._expected_registry_path(package)

        if self._service.calibration_path != expected_cal_path:
            errors.append(
                f"calibration_path mismatch: "
                f"{self._service.calibration_path} != {expected_cal_path}"
            )
        if str(self._service.calibration_version) != expected_version:
            errors.append(
                f"calibration_version mismatch: "
                f"{self._service.calibration_version} != {expected_version}"
            )
        if self._service.rule_registry_path is None or Path(self._service.rule_registry_path) != expected_registry:
            errors.append(
                f"registry_path mismatch: "
                f"{self._service.rule_registry_path} != {expected_registry}"
            )
        # 确认 registry 文件存在且内容对应预期
        if not expected_registry.is_file():
            errors.append(f"expected registry file missing: {expected_registry}")
        else:
            expected_data = self._service._load_registry(expected_registry)
            if self._service.registry != expected_data:
                errors.append("registry content does not match expected registry file")
        return errors

    def _safe_runtime_activate(
        self,
        new_package: dict[str, Any],
        previous_active: dict[str, Any] | None,
    ) -> None:
        """激活运行时服务，失败时补偿恢复 DB 和 runtime 到切换前状态。

        事务流程：
        1. DB 已切 target（调用前完成）
        2. activate target（含 registry 设置）
        3. verify target runtime
        4. 任一失败 → restore previous DB/runtime → verify previous
        5. 恢复成功 → 明确报"失败但已恢复"
        6. 恢复失败 → 严重 RuntimeError，不吞异常

        只有最终状态核对确认 DB 与 runtime 都已恢复时才报告"已恢复"；
        补偿恢复本身失败时抛严重错误，不吞异常、不声称已恢复。
        """
        original_error: Exception | None = None
        try:
            self._activate_service(new_package)
            # Post-activation verification
            post_errors = self._verify_runtime_package(new_package)
            if not post_errors:
                return
            original_error = RuntimeError(
                f"post-activation verification failed: {'; '.join(post_errors)}"
            )
        except Exception as exc:
            original_error = exc

        # ── 激活失败，开始恢复 ──
        if previous_active is None:
            raise RuntimeError(
                f"运行时激活失败且没有切换前版本可恢复：{original_error}"
            ) from original_error

        recovery_errors: list[str] = []

        # 1. DB 恢复
        try:
            self.store.activate_calibration(previous_active["id"])
        except Exception as restore_error:
            recovery_errors.append(f"DB 恢复失败: {restore_error}")

        # 2. Runtime 恢复（含 registry）
        try:
            self._activate_service(previous_active)
        except Exception as restore_error:
            recovery_errors.append(f"运行时恢复失败: {restore_error}")

        # 3. 最终状态核对：DB active
        db_active = self.store.get_active_calibration()
        if db_active is None or db_active["id"] != previous_active["id"]:
            recovery_errors.append("最终核对：DB active 不是切换前版本")

        # 4. 最终状态核对：runtime（calibration + registry）
        runtime_errors = self._verify_runtime_package(previous_active)
        if runtime_errors:
            recovery_errors.extend(
                f"最终核对：{err}" for err in runtime_errors
            )

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
        sample_count = sum(
            1 for sample in samples if str(sample.get("sample_id") or "").strip()
        )
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
            # 生命周期守卫：废弃数据目录不得被陈旧会话的校准写入复活
            ensure_data_dir_allowed(self.paths.data_dir)
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
                    "sample_count": sample_count,
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
        else:
            metadata = dict(existing.get("metadata") or {})
            if metadata.get("sample_count") != sample_count:
                metadata["sample_count"] = sample_count
                self.store.update_calibration_package_metadata(existing["id"], metadata)
                existing["metadata"] = metadata
            if not Path(existing["path"]).is_file():
                target = Path(existing["path"])
                ensure_data_dir_allowed(self.paths.data_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        active = self.store.get_active_calibration()
        active_valid = False
        if active is not None:
            try:
                self._read_json_payload(Path(active["path"]))
                # Formal Bundle 额外验证完整性（防篡改）
                if active.get("metadata", {}).get("formal_bundle"):
                    try:
                        self._verify_formal_bundle_integrity(active)
                    except RuntimeError:
                        active_valid = False
                    else:
                        active_valid = True
                else:
                    active_valid = True
            except (OSError, ValueError):
                active_valid = False
        if not active_valid:
            active = self.store.activate_calibration(existing["id"])
        return active

    # ------------------------------------------------------------------
    # Formal Bundle import
    # ------------------------------------------------------------------

    def _import_formal_bundle(
        self, source: Path, package_dir: Path, digest: str
    ) -> dict[str, Any]:
        """Validate and store a Formal Calibration Runtime Bundle V1 (inactive).

        The bundle is saved with all 6 files but NOT activated.
        Raises on any validation failure; cleans up package_dir.
        """
        bundle: ValidatedFormalBundle = validate_formal_bundle_zip(source)
        manifest = bundle.manifest

        # Save extracted members to package_dir
        original_target = package_dir / source.name  # already copied by caller
        # Write the 5 JSON members
        (package_dir / "formal_package_manifest.json").write_bytes(
            bundle.member_bytes["formal_package_manifest.json"]
        )
        (package_dir / "runtime_calibration.json").write_bytes(
            bundle.member_bytes["runtime_calibration.json"]
        )
        (package_dir / "packaging_rule_registry_v1.json").write_bytes(
            bundle.member_bytes["packaging_rule_registry_v1.json"]
        )
        (package_dir / "validated_rule_package.json").write_bytes(
            bundle.member_bytes["validated_rule_package.json"]
        )
        (package_dir / "promotion_receipt.json").write_bytes(
            bundle.member_bytes["promotion_receipt.json"]
        )

        runtime_path = package_dir / "runtime_calibration.json"
        registry_path = package_dir / "packaging_rule_registry_v1.json"

        version = manifest["calibration_version"]

        # 使用经过交叉验证的真实值，不信任 manifest 自报摘要
        actual_validated_ids = sorted(
            str(rule.get("rule_id"))
            for rule in bundle.validated_package.get("rules", [])
            if isinstance(rule, dict) and rule.get("enabled") is True
        )
        metadata = {
            "formal_bundle": True,
            "contract_version": manifest["contract_version"],
            "package_id": manifest["package_id"],
            "engine_version": manifest["engine_version"],
            "baseline_calibration_version": manifest["baseline_calibration_version"],
            "sha256": digest,
            "runtime_sha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
            "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "validated_package_sha256": manifest["source_fingerprints"]["validated_rule_package_sha256"],
            "promotion_receipt_sha256": manifest["source_fingerprints"]["promotion_receipt_sha256"],
            "original_name": source.name,
            "imported_at": datetime.now(UTC).isoformat(),
            "sample_count": len(bundle.runtime_calibration),
            "aggregate_rule_count": len(bundle.runtime_registry.get("aggregate_rules", [])),
            "sample_rule_count": len(bundle.runtime_registry.get("sample_rules", [])),
            "validated_rule_ids": actual_validated_ids,
        }

        # Register as INACTIVE
        package_id = self.store.register_calibration_package(
            version=version,
            path=str(runtime_path),
            metadata=metadata,
            activate=False,
        )
        return next(
            item for item in self.store.list_calibration_packages() if item["id"] == package_id
        )

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

            # ── Formal Bundle detection (ZIP only) ──
            if path.suffix.lower() == ".zip" and is_formal_bundle_zip(path):
                result = self._import_formal_bundle(path, package_dir, digest)
                return result

            # ── Legacy import ──
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

    # ------------------------------------------------------------------
    # Activation with formal bundle tamper checks
    # ------------------------------------------------------------------

    def _verify_formal_bundle_integrity(self, package: dict[str, Any]) -> None:
        """Re-verify formal bundle runtime files haven't been tampered with since import."""
        metadata = package.get("metadata", {})
        runtime_path = Path(package["path"])
        registry_path = runtime_path.with_name("packaging_rule_registry_v1.json")

        if not runtime_path.is_file():
            raise RuntimeError("formal bundle runtime_calibration.json missing")
        if not registry_path.is_file():
            raise RuntimeError("formal bundle packaging_rule_registry_v1.json missing")

        actual_runtime_sha = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
        if actual_runtime_sha != metadata.get("runtime_sha256"):
            raise RuntimeError("formal bundle runtime_calibration.json has been tampered with (SHA-256 mismatch)")

        actual_registry_sha = hashlib.sha256(registry_path.read_bytes()).hexdigest()
        if actual_registry_sha != metadata.get("registry_sha256"):
            raise RuntimeError("formal bundle registry has been tampered with (SHA-256 mismatch)")

        # Re-validate runtime calibration is still a valid non-empty list
        try:
            runtime_data = json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"formal bundle runtime_calibration.json is corrupt: {exc}") from exc
        if not isinstance(runtime_data, list) or not runtime_data:
            raise RuntimeError("formal bundle runtime_calibration.json must be a non-empty list")
        if not all(isinstance(item, dict) for item in runtime_data):
            raise RuntimeError("formal bundle runtime_calibration.json members must all be objects")

        # Re-validate registry is still valid
        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"formal bundle registry is corrupt: {exc}") from exc
        if not isinstance(registry_data, dict):
            raise RuntimeError("formal bundle registry must be a JSON object")
        for key in ("aggregate_rules", "sample_rules"):
            val = registry_data.get(key)
            if not isinstance(val, list) or not all(isinstance(item, dict) for item in val):
                raise RuntimeError(f"formal bundle registry.{key} must be a list of objects")

    def activate(self, package_id: str) -> dict[str, Any]:
        """启用任意已注册版本，并同步切换运行时包装估算服务。

        不存在的 package 由 store 抛 KeyError；运行时激活失败时
        DB 和 runtime 均恢复到切换前状态，保证一致性。

        Formal Bundle 启用前额外校验文件完整性（防篡改）。
        """
        target = next(
            (item for item in self.store.list_calibration_packages() if item["id"] == package_id),
            None,
        )
        if target is None:
            raise KeyError(package_id)

        # Formal bundle: verify integrity before activation
        if target.get("metadata", {}).get("formal_bundle"):
            self._verify_formal_bundle_integrity(target)

        previous_active = self.active_package()
        active = self.store.activate_calibration(package_id)
        # _safe_runtime_activate 统一处理：activate + post-verification + rollback
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
            ensure_data_dir_allowed(self.paths.data_dir)
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
