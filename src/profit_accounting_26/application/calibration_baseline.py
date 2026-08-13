from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from profit_accounting_26.application.calibration_manager import CalibrationManager
from profit_accounting_26.application.formal_bundle_importer import (
    FormalBundleValidationError,
    validate_formal_bundle_zip,
)
from profit_accounting_26.shared.paths import ApplicationPaths
from profit_accounting_26.storage import SQLiteStore


CURRENT_BASELINE_VERSION = "runtime-safety-baseline-v1"
CURRENT_BASELINE_RESOURCE = "calibration/runtime_safety_baseline/calibration.json"
CURRENT_REGISTRY_RESOURCE = "calibration/logistics_v2/packaging_rule_registry_v1.json"
_CLEANUP_FLAG = "runtime_safety_baseline_cleanup_v1_done"
_LEGACY_BUNDLED_BASELINE_VERSIONS = frozenset(
    {
        "local-calibration-v3-77-samples",
        "local-calibration-v3-77-samples-rules-v1",
    }
)


def _safe_remove_package_dir(package: dict[str, Any], paths: ApplicationPaths) -> None:
    raw_path = str(package.get("path") or "").strip()
    if not raw_path:
        return
    try:
        package_dir = Path(raw_path).resolve().parent
        base_dir = paths.calibration_packages_dir.resolve()
        package_dir.relative_to(base_dir)
    except (OSError, ValueError):
        return
    if package_dir == base_dir:
        return
    shutil.rmtree(package_dir, ignore_errors=True)


def purge_obsolete_bundled_calibration(store: SQLiteStore, paths: ApplicationPaths) -> None:
    """One-time local migration that removes bundled calibration from older releases.

    It removes obsolete builtin package registrations/files and Formal Bundles
    known to have been built on the retired bundled baseline.  Product history,
    feedback exports, API settings and unrelated user files are not touched.
    """

    if store.get_setting(_CLEANUP_FLAG, False):
        return

    for package in list(store.list_calibration_packages()):
        metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
        version = str(package.get("version") or "")
        baseline_version = str(metadata.get("baseline_calibration_version") or "")
        obsolete_builtin = bool(metadata.get("builtin")) and version != CURRENT_BASELINE_VERSION
        obsolete_formal = bool(metadata.get("formal_bundle")) and (
            baseline_version in _LEGACY_BUNDLED_BASELINE_VERSIONS
        )
        if not (obsolete_builtin or obsolete_formal):
            continue
        try:
            store.delete_calibration_package(str(package["id"]))
        except KeyError:
            pass
        _safe_remove_package_dir(package, paths)

    # Older releases stored the bundled calibration copy in this fixed folder.
    # The new neutral baseline is recreated immediately afterwards by ensure_builtin.
    shutil.rmtree(paths.calibration_packages_dir / "builtin", ignore_errors=True)
    store.set_setting(_CLEANUP_FLAG, True)


class CurrentBaselineCalibrationManager(CalibrationManager):
    """Calibration manager that accepts Formal Bundles for the current baseline only."""

    def _import_formal_bundle(self, source: Path, package_dir: Path, digest: str) -> dict[str, Any]:
        bundle = validate_formal_bundle_zip(source)
        baseline_version = str(bundle.manifest.get("baseline_calibration_version") or "")
        if baseline_version != CURRENT_BASELINE_VERSION:
            raise FormalBundleValidationError(
                "校准包基线版本与当前软件不一致。请基于当前空校准基线重新验证并构建 Formal Bundle。"
            )
        return super()._import_formal_bundle(source, package_dir, digest)
