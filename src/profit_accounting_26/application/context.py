from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from profit_accounting_26.application.calibration_manager import CalibrationManager
from profit_accounting_26.application.calibration_feedback_service import CalibrationFeedbackService
from profit_accounting_26.application.calibration_export_service import CalibrationFeedbackExporter
from profit_accounting_26.application.diagnostic_logger import DiagnosticLogger
from profit_accounting_26.application.api_profile_store import ApiProfileStore
from profit_accounting_26.application.history_record_service import HistoryRecordV2Service
from profit_accounting_26.application.local_reestimate_service import LocalReestimateService
from profit_accounting_26.application.packaging_estimation_service import PackagingEstimationService
from profit_accounting_26.application.recognition_service import RecognitionService
from profit_accounting_26.application.record_service import RecordService
from profit_accounting_26.application.runtime_ai_services import (
    RuntimeLocalReestimateService,
    RuntimePackagingArbitrator,
    RuntimeRecognitionService,
)
from profit_accounting_26.application.settings_service import SettingsService
from profit_accounting_26.shared import ApplicationPaths, resource_path
from profit_accounting_26.storage import SQLiteStore
from profit_accounting_26.storage.image_store import ImageStore


@dataclass(slots=True)
class AppContext:
    paths: ApplicationPaths
    store: SQLiteStore
    settings_service: SettingsService
    packaging_service: PackagingEstimationService
    record_service: RecordService
    calibration_manager: CalibrationManager
    recognition_service: RuntimeRecognitionService
    api_profile_store: ApiProfileStore
    local_reestimate_service: RuntimeLocalReestimateService
    diagnostic_logger: DiagnosticLogger
    history_record_v2_service: HistoryRecordV2Service
    image_store: ImageStore
    calibration_feedback_service: CalibrationFeedbackService
    calibration_export_service: CalibrationFeedbackExporter

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
        # 根据 active calibration 类型决定 registry 路径：
        # Formal Bundle → sibling packaging_rule_registry_v1.json
        # Legacy / builtin → CAL77 resource registry
        # 注意：此 packaging_service 继续由 CalibrationManager 维护完整校准状态；
        # 正常 AI 运行是否允许规则参与，由 RuntimePackagingArbitrator 决定。
        if active_calibration.get("metadata", {}).get("formal_bundle"):
            _registry_path = Path(active_calibration["path"]).with_name(
                "packaging_rule_registry_v1.json"
            )
        else:
            _registry_path = resource_path(
                "calibration/logistics_v2/packaging_rule_registry_v1.json"
            )
        packaging_service = PackagingEstimationService(
            active_calibration["path"],
            calibration_version=str(active_calibration["version"]),
            rule_registry_path=_registry_path,
        )
        calibration_manager.bind_service(packaging_service)
        api_profile_store = ApiProfileStore(paths.data_dir)
        diagnostic_logger = DiagnosticLogger(paths.data_dir, settings_service.load())
        image_store = ImageStore(store, paths.data_dir)
        image_store.initialize()
        history_record_v2_service = HistoryRecordV2Service(store)
        calibration_feedback_service = CalibrationFeedbackService(store)
        calibration_feedback_service.initialize()
        calibration_export_service = CalibrationFeedbackExporter(
            data_dir=paths.data_dir,
            feedback_service=calibration_feedback_service,
        )

        # Production AI chain:
        # frozen V1.2 AI -> deterministic PackagingEstimationService safety arbitration
        # -> deterministic logistics/profit.
        # Legacy/builtin CAL77 rules remain available for audit/offline work but are
        # not allowed to change runtime values; only validated Formal Bundle rules
        # may participate after explicit activation.
        runtime_packaging = RuntimePackagingArbitrator(
            packaging_service,
            calibration_manager,
        )
        recognition_service = RuntimeRecognitionService(
            RecognitionService(settings_service, api_profile_store),
            runtime_packaging,
        )
        local_reestimate_service = RuntimeLocalReestimateService(
            LocalReestimateService(api_profile_store),
            runtime_packaging,
        )

        return cls(
            paths=paths,
            store=store,
            settings_service=settings_service,
            packaging_service=packaging_service,
            record_service=RecordService(
                store,
                paths,
                image_store=image_store,
                history_service=history_record_v2_service,
                feedback_service=calibration_feedback_service,
            ),
            calibration_manager=calibration_manager,
            recognition_service=recognition_service,
            api_profile_store=api_profile_store,
            local_reestimate_service=local_reestimate_service,
            diagnostic_logger=diagnostic_logger,
            history_record_v2_service=history_record_v2_service,
            image_store=image_store,
            calibration_feedback_service=calibration_feedback_service,
            calibration_export_service=calibration_export_service,
        )
