from __future__ import annotations

from dataclasses import dataclass

from profit_accounting_26.application.calibration_manager import CalibrationManager
from profit_accounting_26.application.api_profile_store import ApiProfileStore
from profit_accounting_26.application.import_export_service import ImportExportService
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.application.record_service import RecordService
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.shared import ApplicationPaths, resource_path
from profit_accounting_26.storage import SQLiteStore


@dataclass(slots=True)
class AppContext:
    paths: ApplicationPaths
    store: SQLiteStore
    settings_service: SettingsService
    packaging_service: PackagingEstimationService
    record_service: RecordService
    import_export_service: ImportExportService
    calibration_manager: CalibrationManager
    recognition_service: RecognitionService
    api_profile_store: ApiProfileStore
    local_reestimate_service: LocalReestimateService

    @classmethod
    def create_default(cls) -> "AppContext":
        paths = ApplicationPaths.default()
        paths.ensure()
        store = SQLiteStore(paths.database_path)
        store.initialize()
        settings_service = SettingsService(
            paths.settings_path,
            defaults_path=resource_path("config/defaults.json"),
        )
        # Create a local settings file immediately so the UI has one source of truth.
        settings_service.load()
        calibration_manager = CalibrationManager(store, paths)
        active_calibration = calibration_manager.ensure_builtin(
            resource_path("calibration/logistics_v2/calibration_all_cleaned_v3.json"),
            version=PackagingEstimationService.CALIBRATION_VERSION,
        )
        packaging_service = PackagingEstimationService(
            active_calibration["path"],
            calibration_version=str(active_calibration["version"]),
            rule_registry_path=resource_path("calibration/logistics_v2/packaging_rule_registry_v1.json"),
        )
        calibration_manager.bind_service(packaging_service)
        api_profile_store = ApiProfileStore(paths.data_dir)
        return cls(
            paths=paths,
            store=store,
            settings_service=settings_service,
            packaging_service=packaging_service,
            record_service=RecordService(store, paths),
            import_export_service=ImportExportService(store),
            calibration_manager=calibration_manager,
            recognition_service=RecognitionService(settings_service, api_profile_store),
            api_profile_store=api_profile_store,
            local_reestimate_service=LocalReestimateService(api_profile_store),
        )
