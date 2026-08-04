"""设置页 Binder。

绑定 ``settings_page.ui`` 中的控件到现有 ``SettingsService`` / ``ApiProfileStore``。

本 Binder 为设置页迁移准备：当 SettingsPage 从程序化构建切换为 .ui 加载时，
此 Binder 负责按 objectName 绑定所有控件。

当前状态：骨架实现，绑定基础设置和 API Profile 选择。
货代表格和利润规则编辑器继续复用现有 SettingsPage 逻辑。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QWidget,
)

from profit_accounting_26.application import AppContext


class SettingsBinder(QObject):
    """设置页 Binder，绑定 settings_page.ui 控件。"""

    settingsSaved = Signal()
    dirtyChanged = Signal(bool)

    def __init__(self, page: QWidget, context: AppContext) -> None:
        super().__init__(page)
        self.page = page
        self.context = context
        self.settings = context.settings_service.load()
        self._dirty = False
        self._find_widgets()
        self._connect_signals()
        self._hide_placeholder_controls()
        self.load_settings()

    def _find_widgets(self) -> None:
        f = self.page.findChild
        # 基础设置
        self.txt_display_name: QLineEdit = f(QLineEdit, "txtDisplayName")
        self.cmb_log_level: QComboBox = f(QComboBox, "cmbLogLevel")
        self.spin_log_retention: QDoubleSpinBox = f(QDoubleSpinBox, "spinLogRetentionDays")
        self.txt_log_directory: QLineEdit = f(QLineEdit, "txtLogDirectory")
        self.btn_open_log_dir: QPushButton = f(QPushButton, "btnOpenLogDirectory")
        self.btn_save: QPushButton = f(QPushButton, "btnSaveSettings")
        self.btn_discard: QPushButton = f(QPushButton, "btnDiscardSettings")
        # API Profile
        self.cmb_profile_select: QComboBox = f(QComboBox, "cmbApiProfileSelect")
        self.btn_add_api: QPushButton = f(QPushButton, "btnAddApiConfig")
        self.cmb_vision_binding: QComboBox = f(QComboBox, "cmbVisionApiConfig")
        self.cmb_partial_binding: QComboBox = f(QComboBox, "cmbPartialEstimateApiConfig")
        self.txt_profile_name: QLineEdit = f(QLineEdit, "txtApiProfileName")
        self.cmb_provider: QComboBox = f(QComboBox, "cmbApiProvider")
        self.txt_endpoint: QLineEdit = f(QLineEdit, "txtApiEndpoint")
        self.txt_model: QLineEdit = f(QLineEdit, "txtApiModel")
        self.txt_api_key: QLineEdit = f(QLineEdit, "txtApiKey")
        self.btn_show_key: QPushButton = f(QPushButton, "btnShowApiKey1")
        self.btn_save_api: QPushButton = f(QPushButton, "btnSaveApiProfile")
        self.btn_test_api: QPushButton = f(QPushButton, "btnTestApi1")
        self.btn_delete_api: QPushButton = f(QPushButton, "btnDeleteApi1")
        # 货代
        self.table_forwarders: QTableWidget = f(QTableWidget, "tableForwarders")
        self.btn_add_forwarder: QPushButton = f(QPushButton, "btnAddFreightForwarder")
        self.btn_save_forwarders: QPushButton = f(QPushButton, "btnSaveForwarders")
        # 利润规则
        self.list_rules = f(__import__("PySide6.QtWidgets", fromlist=["QListWidget"]).QListWidget, "listProfitRules")
        self.btn_add_rule: QPushButton = f(QPushButton, "btnAddProfitRule")
        self.btn_save_rule: QPushButton = f(QPushButton, "btnSaveProfitRule")
        self.btn_disable_rule: QPushButton = f(QPushButton, "btnDisableProfitRule")
        self.btn_archive_rule: QPushButton = f(QPushButton, "btnArchiveProfitRule")
        self.btn_delete_rule: QPushButton = f(QPushButton, "btnDeleteProfitRule")

    def _hide_placeholder_controls(self) -> None:
        """隐藏 .ui 中的 Designer 预览控件（第2、3行 API 配置、测试/删除按钮）。

        契约 §13.2：UI 中第 2、3 行静态 API 控件是设计预览，运行时隐藏。
        btnTestApi1 / btnDeleteApi1 及第 2、3 行同类按钮在运行时隐藏。
        """
        # 隐藏测试和删除按钮（当前没有真实业务）
        for btn in [self.btn_test_api, self.btn_delete_api]:
            if btn:
                btn.setVisible(False)
        # 隐藏第 2、3 行 API 预览控件（按 objectName 模式查找）
        for suffix in ["2", "3"]:
            for prefix in ["btnShowApiKey", "btnTestApi", "btnDeleteApi", "cmbVisionApiConfig", "cmbPartialEstimateApiConfig"]:
                widget = self.page.findChild(QWidget, f"{prefix}{suffix}")
                if widget:
                    widget.setVisible(False)

    def _connect_signals(self) -> None:
        if self.btn_save:
            self.btn_save.clicked.connect(self.save_settings)
        if self.btn_discard:
            self.btn_discard.clicked.connect(self.load_settings)
        if self.btn_show_key:
            self.btn_show_key.setCheckable(True)
            self.btn_show_key.toggled.connect(self._toggle_api_key_visibility)
        if self.txt_display_name:
            self.txt_display_name.textChanged.connect(self._mark_dirty)
        if self.cmb_log_level:
            self.cmb_log_level.currentIndexChanged.connect(self._mark_dirty)

    def _toggle_api_key_visibility(self, visible: bool) -> None:
        """临时显示/隐藏 API Key，不写日志、不复制、不持久化明文状态。"""
        if self.txt_api_key:
            self.txt_api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )

    def _mark_dirty(self, *args) -> None:
        self._dirty = True
        self.dirtyChanged.emit(True)

    @property
    def dirty(self) -> bool:
        return self._dirty

    def load_settings(self) -> None:
        """从 SettingsService 加载设置到 UI。"""
        self.settings = self.context.settings_service.load()
        if self.txt_display_name:
            with QSignalBlocker(self.txt_display_name):
                self.txt_display_name.setText(str(self.settings.get("display_name") or ""))
        if self.cmb_log_level:
            with QSignalBlocker(self.cmb_log_level):
                level = str(self.settings.get("log_level") or "INFO")
                idx = self.cmb_log_level.findText(level)
                if idx >= 0:
                    self.cmb_log_level.setCurrentIndex(idx)
        if self.spin_log_retention:
            with QSignalBlocker(self.spin_log_retention):
                self.spin_log_retention.setValue(float(self.settings.get("log_retention_days", 30)))
        if self.txt_log_directory:
            self.txt_log_directory.setText(str(self.context.paths.log_dir))
        if self.txt_api_key:
            self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._dirty = False
        self.dirtyChanged.emit(False)

    def save_settings(self) -> None:
        """保存设置到 SettingsService。"""
        if self.txt_display_name:
            self.settings["display_name"] = self.txt_display_name.text().strip()
        if self.cmb_log_level:
            self.settings["log_level"] = self.cmb_log_level.currentText()
        if self.spin_log_retention:
            self.settings["log_retention_days"] = int(self.spin_log_retention.value())
        self.context.settings_service.save(self.settings)
        self._dirty = False
        self.dirtyChanged.emit(False)
        self.settingsSaved.emit()
