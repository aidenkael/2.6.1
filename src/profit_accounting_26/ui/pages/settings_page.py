"""设置页 —— 冻结 UI 绑定版（2.6.1-dual-profit）。

布局完全来自 ``forms/settings_page.ui``（QUiLoader 运行时加载，不生成 Python 布局副本）；
控件按 ``objectName`` 用 ``findChild`` 获取。

与旧版一致的业务能力：
- 基础设置（显示名称、日志级别、日志保留天数、日志目录）；
- API Profile 管理（新建/更新配置、私钥、视觉/局部重估绑定、供应商预设）；
- 货代管理（新增、归档过滤、表格校验、独立保存）；
- 利润调整规则（新增、编辑、启用/停用、归档、删除）；
- 保存/放弃修改；跨目录镜像；三个信号保持不变。

运行时处理（契约 §13.2）：
- API 配置第 2、3 行 Designer 预览控件隐藏；``btnTestApi1``/``btnDeleteApi1`` 隐藏；
- 下拉框的 Designer 预览项替换为真实运行时数据（供应商预设、API 配置、
  规则引擎合法的条件字段/比较方式/调整方向/币种/百分比基数）。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext, ApiProfile, ApiProfileStore, LOCAL_REESTIMATE, SettingsService, VISUAL_AI
from profit_accounting_26.application.api_profile_store import PROVIDER_PRESETS
from profit_accounting_26.domain.models import Forwarder
from profit_accounting_26.domain.rules import (
    AdjustmentDirection,
    AdjustmentRule,
    AdjustmentType,
    CompareOp,
)
from profit_accounting_26.shared import ApplicationPaths
from profit_accounting_26.ui.ui_loader import load_settings_page
from profit_accounting_26.ui.widgets import confirm_action


class SettingsPage(QWidget):
    settingsSaved = Signal()
    forwardersSaved = Signal()
    dirtyChanged = Signal(bool)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.settings = context.settings_service.load()
        self.dirty = False
        self._updating = False
        self._show_archived_forwarders = False
        self.visible_rule_indices: list[int] = []
        self.rules_data: list[dict] = []

        # 从冻结 .ui 加载整页布局
        root = load_settings_page(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(root)
        self._root = root

        self._find_widgets()
        self._hide_preview_controls()
        self._init_runtime_items()
        self._connect_signals()
        self._setup_forwarder_table()
        self.load_settings()

    # ------------------------------------------------------------------
    # 控件查找
    # ------------------------------------------------------------------

    def _find_widgets(self) -> None:
        f = self._root.findChild
        # 基础设置
        self.display_name = f(QLineEdit, "txtDisplayName")
        self.log_level = f(QComboBox, "cmbLogLevel")
        if self.log_level:
            self.log_level.setToolTip(
                "DEBUG：最详细，仅开发排查时使用\n"
                "INFO：记录正常运行信息，推荐日常使用\n"
                "WARNING：只记录警告和错误\n"
                "ERROR：只记录错误"
            )
        self.log_retention_days = f(QDoubleSpinBox, "spinLogRetentionDays")
        self.log_directory = f(QLineEdit, "txtLogDirectory")
        self.btn_open_log_dir = f(QPushButton, "btnOpenLogDirectory")
        self.btn_save = f(QPushButton, "btnSaveSettings")
        self.btn_discard = f(QPushButton, "btnDiscardSettings")
        # API Profile
        self.api_profile_select = f(QComboBox, "cmbApiProfileSelect")
        self.btn_add_api = f(QPushButton, "btnAddApiConfig")
        self.visual_binding = f(QComboBox, "cmbVisionApiConfig")
        self.local_binding = f(QComboBox, "cmbPartialEstimateApiConfig")
        self.api_profile_name = f(QLineEdit, "txtApiProfileName")
        self.api_provider = f(QComboBox, "cmbApiProvider")
        self.vision_endpoint = f(QLineEdit, "txtApiEndpoint")
        self.vision_model = f(QLineEdit, "txtApiModel")
        self.vision_key = f(QLineEdit, "txtApiKey")
        self.btn_show_key = f(QPushButton, "btnShowApiKey1")
        self.btn_save_api = f(QPushButton, "btnSaveApiProfile")
        # 货代
        self.show_active = f(QPushButton, "btnShowActiveFreight")
        self.show_archived = f(QPushButton, "btnShowArchivedFreight")
        self.btn_add_forwarder = f(QPushButton, "btnAddFreightForwarder")
        self.btn_save_forwarders = f(QPushButton, "btnSaveForwarders")
        self.forwarder_table = f(QTableWidget, "tableForwarders")
        # 利润规则
        self.btn_add_rule = f(QPushButton, "btnAddProfitRule")
        self.rule_list = f(QListWidget, "listProfitRules")
        self.rule_name = f(QLineEdit, "txtRuleName")
        self.rule_condition_field = f(QComboBox, "cmbRuleConditionField")
        self.rule_compare = f(QComboBox, "cmbRuleCompareMode")
        self.rule_condition_value = f(QDoubleSpinBox, "spinRuleConditionValue")
        self.rule_direction = f(QComboBox, "cmbRuleAdjustmentDirection")
        self.rule_type = f(QComboBox, "cmbRuleAdjustmentType")
        self.rule_value = f(QDoubleSpinBox, "spinRuleAdjustmentValue")
        self.rule_currency = f(QComboBox, "cmbRuleCurrency")
        self.rule_percent_base = f(QComboBox, "cmbRulePercentBase")
        self.rule_description = f(QTextEdit, "txtRuleDescription")
        self.btn_save_rule = f(QPushButton, "btnSaveProfitRule")
        self.btn_disable_rule = f(QPushButton, "btnDisableProfitRule")
        self.btn_archive_rule = f(QPushButton, "btnArchiveProfitRule")
        self.btn_delete_rule = f(QPushButton, "btnDeleteProfitRule")
        # 物流校准规则
        self.calibration_table = f(QTableWidget, "tableCalibrationPackages")
        self.btn_import_calibration = f(QPushButton, "btnImportCalibrationPackage")
        self.btn_activate_calibration = f(QPushButton, "btnActivateCalibrationPackage")
        self.btn_delete_calibration = f(QPushButton, "btnDeleteCalibrationPackage")
        self.calibration_status = f(QLabel, "lblCalibrationActiveStatus")

    def _hide_preview_controls(self) -> None:
        """契约 §13.2：隐藏 Designer 预览行与无真实业务的测试/删除按钮。
        例外：btnDeleteApi1 改为可见删除按钮。"""
        for name in ("btnTestApi1",):
            widget = self._root.findChild(QWidget, name)
            if widget:
                widget.setVisible(False)
        # btnDeleteApi1：改为可见并配置为删除按钮
        self.btn_delete_api = self._root.findChild(QPushButton, "btnDeleteApi1")
        if self.btn_delete_api:
            self.btn_delete_api.setText("删除配置")
            self.btn_delete_api.setVisible(True)
            self.btn_delete_api.clicked.connect(self._delete_api_profile)
            self.btn_delete_api.setEnabled(False)
        for suffix in ("2", "3"):
            for prefix in (
                "txtApiConfigName", "cmbApiProvider", "txtApiEndpoint",
                "txtApiModel", "txtApiKey", "btnShowApiKey", "btnSaveApi",
                "btnDeleteApi", "btnTestApi",
            ):
                widget = self._root.findChild(QWidget, f"{prefix}{suffix}")
                if widget:
                    widget.setVisible(False)

    def _init_runtime_items(self) -> None:
        """把 Designer 预览下拉项替换为与引擎/存储一致的真实取值。"""
        # 供应商预设
        self.api_provider.clear()
        self.api_provider.addItems(PROVIDER_PRESETS.keys())
        # 规则条件字段（与 calculate_profit 的 rule_context 键一致）
        self.rule_condition_field.clear()
        self.rule_condition_field.addItem("最终售价（美元）", "sale_price_usd")
        self.rule_condition_field.addItem("最终售价（人民币）", "sale_price_rmb")
        self.rule_condition_field.addItem("系统总成本（人民币）", "total_cost_rmb")
        # 比较方式
        self.rule_compare.clear()
        for text, value in (("小于", "lt"), ("小于等于", "lte"), ("大于", "gt"), ("大于等于", "gte"), ("等于", "eq")):
            self.rule_compare.addItem(text, value)
        # 调整方向
        self.rule_direction.clear()
        self.rule_direction.addItem("增加收入", "income")
        self.rule_direction.addItem("增加成本", "cost")
        # 调整类型
        self.rule_type.clear()
        self.rule_type.addItem("固定金额", "fixed")
        self.rule_type.addItem("百分比", "percent")
        # 币种
        self.rule_currency.clear()
        self.rule_currency.addItems(["USD", "RMB"])
        # 百分比基数（与 rule_context 键一致）
        self.rule_percent_base.clear()
        self.rule_percent_base.addItem("不适用", None)
        self.rule_percent_base.addItem("最终售价人民币", "sale_price_rmb")
        self.rule_percent_base.addItem("预留后收入", "revenue_after_reserve_rmb")
        self.rule_percent_base.addItem("计算采用总成本", "total_cost_rmb")
        # 数值范围
        for spin in (self.rule_condition_value, self.rule_value):
            spin.setRange(0, 1_000_000)
            spin.setDecimals(4)
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        if self.log_retention_days:
            self.log_retention_days.setRange(1, 3650)
            self.log_retention_days.setDecimals(0)
        # 日志目录只读
        if self.log_directory:
            self.log_directory.setReadOnly(True)
        # API Key 默认密文
        if self.vision_key:
            self.vision_key.setEchoMode(QLineEdit.EchoMode.Password)
        # 过滤按钮为可切换状态
        for button in (self.show_active, self.show_archived):
            if button:
                button.setCheckable(True)
        self._setup_calibration_table()

    def _connect_signals(self) -> None:
        if self.btn_save:
            self.btn_save.clicked.connect(self.save_settings)
        if self.btn_discard:
            self.btn_discard.clicked.connect(self.load_settings)
        if self.btn_open_log_dir:
            self.btn_open_log_dir.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.context.paths.data_dir / "logs")))
            )
        if self.api_profile_select:
            self.api_profile_select.currentIndexChanged.connect(self._load_selected_api_profile)
        if self.btn_add_api:
            self.btn_add_api.clicked.connect(self._new_api_profile)
        if self.api_provider:
            self.api_provider.currentTextChanged.connect(self._apply_provider_preset)
        if self.btn_show_key:
            self.btn_show_key.setCheckable(True)
            self.btn_show_key.toggled.connect(self._toggle_api_key_visibility)
        if self.btn_save_api:
            self.btn_save_api.clicked.connect(self.save_api_profile)
        if self.show_active:
            self.show_active.clicked.connect(lambda: self.filter_forwarders(False))
        if self.show_archived:
            self.show_archived.clicked.connect(lambda: self.filter_forwarders(True))
        if self.btn_add_forwarder:
            self.btn_add_forwarder.clicked.connect(self.add_forwarder_row)
        if self.btn_save_forwarders:
            self.btn_save_forwarders.clicked.connect(self.save_forwarders_only)
        if self.forwarder_table:
            self.forwarder_table.itemChanged.connect(lambda _item: self._mark_dirty())
        if self.btn_add_rule:
            self.btn_add_rule.clicked.connect(self.add_rule)
        if self.rule_list:
            self.rule_list.currentRowChanged.connect(self.load_rule_editor)
        if self.btn_save_rule:
            self.btn_save_rule.clicked.connect(self.save_current_rule)
        if self.btn_disable_rule:
            self.btn_disable_rule.setCheckable(True)
            self.btn_disable_rule.toggled.connect(self._update_rule_toggle_text)
        if self.btn_archive_rule:
            self.btn_archive_rule.clicked.connect(self.archive_current_rule)
        if self.btn_delete_rule:
            self.btn_delete_rule.clicked.connect(self.delete_current_rule)
        # 物流校准规则
        if self.btn_import_calibration:
            self.btn_import_calibration.clicked.connect(self._import_calibration_package)
        if self.btn_activate_calibration:
            self.btn_activate_calibration.clicked.connect(self._activate_selected_calibration)
        if self.btn_delete_calibration:
            self.btn_delete_calibration.clicked.connect(self._delete_selected_calibration)
        if self.calibration_table:
            self.calibration_table.itemSelectionChanged.connect(self._update_calibration_buttons)
        # 脏标记
        if self.display_name:
            self.display_name.textChanged.connect(lambda _text: self._mark_dirty())
        if self.log_level:
            self.log_level.currentIndexChanged.connect(lambda _index: self._mark_dirty())
        if self.log_retention_days:
            self.log_retention_days.valueChanged.connect(lambda _value: self._mark_dirty())
        if self.visual_binding:
            self.visual_binding.currentIndexChanged.connect(lambda _index: self._mark_dirty())
        if self.local_binding:
            self.local_binding.currentIndexChanged.connect(lambda _index: self._mark_dirty())

    def _setup_forwarder_table(self) -> None:
        if self.forwarder_table is None:
            return
        self.forwarder_table.setHorizontalHeaderLabels(
            ["名称", "头程单价（RMB/kg）", "固定服务费（RMB）", "体积重除数", "启用状态", "操作", "内部ID", "归档"]
        )
        self.forwarder_table.setAlternatingRowColors(True)
        self.forwarder_table.verticalHeader().setVisible(False)
        self.forwarder_table.horizontalHeader().setStretchLastSection(False)
        self.forwarder_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            self.forwarder_table.setColumnWidth(col, 160)
        self.forwarder_table.setColumnWidth(4, 80)
        self.forwarder_table.setColumnWidth(5, 170)
        # 固定行高：容纳复选框与操作按钮垂直居中，不新增横向滚动条
        self.forwarder_table.verticalHeader().setDefaultSectionSize(44)
        self.forwarder_table.setColumnHidden(6, True)
        self.forwarder_table.setColumnHidden(7, True)

    @staticmethod
    def _center_cell(widget: QWidget) -> QWidget:
        """表格单元格容器：让内部控件水平 + 垂直居中。"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        return container

    def _build_forwarder_op_widget(self, identifier: str, archived: bool) -> QWidget:
        """操作列容器：按钮水平 + 垂直居中，最小宽度保证文字不裁切。"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        layout.addStretch(1)
        if archived:
            btn_restore = QPushButton("恢复")
            btn_restore.setMinimumWidth(56)
            btn_restore.clicked.connect(lambda _checked=False, fid=identifier: self.toggle_forwarder_archive(fid))
            layout.addWidget(btn_restore)
            btn_delete = QPushButton("永久删除")
            btn_delete.setMinimumWidth(76)
            btn_delete.clicked.connect(lambda _checked=False, fid=identifier: self._delete_forwarder_permanently(fid))
            layout.addWidget(btn_delete)
        else:
            btn_archive = QPushButton("归档")
            btn_archive.setMinimumWidth(56)
            btn_archive.clicked.connect(lambda _checked=False, fid=identifier: self.toggle_forwarder_archive(fid))
            layout.addWidget(btn_archive)
        layout.addStretch(1)
        return container

    # ------------------------------------------------------------------
    # 脏标记
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if self._updating:
            return
        if not self.dirty:
            self.dirty = True
            self.dirtyChanged.emit(True)

    # ------------------------------------------------------------------
    # 物流校准规则（校准包版本管理）
    # ------------------------------------------------------------------

    def _setup_calibration_table(self) -> None:
        table = self.calibration_table
        if table is None:
            return
        table.setHorizontalHeaderLabels(["版本", "状态", "导入时间", "文件名"])
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 170)
        table.horizontalHeader().setStretchLastSection(True)

    def _refresh_calibration_packages(self) -> None:
        """重新加载校准包版本列表；进入设置页/导入/启用/删除成功后调用。"""
        table = self.calibration_table
        if table is None:
            return
        packages = self.context.calibration_manager.list_packages()
        table.setRowCount(0)
        for package in packages:
            row = table.rowCount()
            table.insertRow(row)
            metadata = package.get("metadata", {})
            file_name = str(metadata.get("original_name") or Path(package["path"]).name)
            if metadata.get("builtin"):
                file_name = f"{file_name}（内置）"
            values = [
                str(package["version"]),
                "当前启用" if package["active"] else "未启用",
                str(package["imported_at"]),
                file_name,
            ]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))
            table.item(row, 0).setData(Qt.ItemDataRole.UserRole, package["id"])
        active = self.context.calibration_manager.active_package()
        if self.calibration_status:
            if active:
                count = active.get("metadata", {}).get("sample_count", "未知")
                self.calibration_status.setText(f"当前启用：{active['version']} · {count} 条样本")
            else:
                self.calibration_status.setText("当前没有启用的校准版本")
        self._update_calibration_buttons()

    def _selected_calibration_package(self) -> dict | None:
        table = self.calibration_table
        if table is None:
            return None
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        package_id = str(item.data(Qt.ItemDataRole.UserRole)) if item else ""
        return next(
            (pkg for pkg in self.context.calibration_manager.list_packages() if pkg["id"] == package_id),
            None,
        )

    def _update_calibration_buttons(self) -> None:
        package = self._selected_calibration_package()
        if self.btn_activate_calibration:
            self.btn_activate_calibration.setEnabled(bool(package) and not package["active"])
        if self.btn_delete_calibration:
            # builtin 受保护：删除按钮对内置版本禁用
            self.btn_delete_calibration.setEnabled(
                bool(package) and not package.get("metadata", {}).get("builtin")
            )

    def _import_calibration_package(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "导入校准包", "", "校准包 (*.json *.zip);;全部文件 (*)")
        if not selected:
            return
        try:
            result = self.context.calibration_manager.import_package(selected)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", str(exc))
            return
        self._refresh_calibration_packages()
        QMessageBox.information(self, "导入成功", f"已导入并启用：{result['version']}")

    def _activate_selected_calibration(self) -> None:
        package = self._selected_calibration_package()
        if package is None:
            QMessageBox.information(self, "启用校准版本", "请先选择一个校准版本。")
            return
        if package["active"]:
            return
        try:
            self.context.calibration_manager.activate(package["id"])
        except Exception as exc:
            QMessageBox.warning(self, "启用失败", str(exc))
            return
        self._refresh_calibration_packages()

    def _delete_selected_calibration(self) -> None:
        package = self._selected_calibration_package()
        if package is None:
            QMessageBox.information(self, "删除校准版本", "请先选择一个校准版本。")
            return
        if package.get("metadata", {}).get("builtin"):
            QMessageBox.information(self, "删除校准版本", "内置校准版本不允许删除。")
            return
        if package["active"]:
            confirmed = confirm_action(
                self,
                "删除当前启用的校准版本",
                f"即将删除当前启用的校准版本：{package['version']}。\n"
                "删除后将自动切换到内置默认校准版本。",
                confirm_text="删除并切换",
                danger=True,
            )
        else:
            confirmed = confirm_action(
                self,
                "删除校准版本",
                f"确定删除校准版本：{package['version']} 吗？",
                confirm_text="删除",
                danger=True,
            )
        if not confirmed:
            return
        try:
            self.context.calibration_manager.delete_package(package["id"])
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self._refresh_calibration_packages()

    # ------------------------------------------------------------------
    # API Profile
    # ------------------------------------------------------------------

    def _refresh_api_profiles(self) -> None:
        public = self.context.api_profile_store.load_public()
        profiles = [item for item in public["profiles"] if isinstance(item, dict)]
        bindings = public["button_bindings"]
        # 视觉识图 / 局部文字重估 下拉框保留"新建配置"
        for combo in (self.visual_binding, self.local_binding):
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("新建配置", "")
            for item in profiles:
                combo.addItem(str(item.get("display_name") or "未命名配置"), str(item.get("profile_id") or ""))
            combo.blockSignals(False)
        # API profile 选择下拉框：只显示已有配置
        if self.api_profile_select is not None:
            self.api_profile_select.blockSignals(True)
            self.api_profile_select.clear()
            self.api_profile_select.addItem("选择已有配置", "")
            for item in profiles:
                self.api_profile_select.addItem(str(item.get("display_name") or "未命名配置"), str(item.get("profile_id") or ""))
            self.api_profile_select.blockSignals(False)
        if self.visual_binding:
            self.visual_binding.setCurrentIndex(max(0, self.visual_binding.findData(bindings.get(VISUAL_AI))))
        if self.local_binding:
            self.local_binding.setCurrentIndex(max(0, self.local_binding.findData(bindings.get(LOCAL_REESTIMATE))))

    def _new_api_profile(self) -> None:
        """新建配置：清空输入字段，进入新建模式。"""
        if self.api_profile_select:
            self.api_profile_select.setCurrentIndex(max(0, self.api_profile_select.findData("")))
        # 清空输入字段
        for field in (self.api_profile_name, self.vision_endpoint, self.vision_model, self.vision_key):
            if field:
                field.clear()
        if self.api_provider:
            self.api_provider.setCurrentText("自定义")
        if self.btn_delete_api:
            self.btn_delete_api.setEnabled(False)

    def _load_selected_api_profile(self, _index: int) -> None:
        if self.api_profile_select is None:
            return
        profile_id = str(self.api_profile_select.currentData() or "")
        # 删除按钮状态：选中已保存配置时启用
        if self.btn_delete_api:
            self.btn_delete_api.setEnabled(bool(profile_id))
        if not profile_id:
            if self.api_profile_name:
                self.api_profile_name.clear()
            if self.api_provider:
                self.api_provider.setCurrentText("自定义")
            if self.vision_endpoint:
                self.vision_endpoint.clear()
            if self.vision_model:
                self.vision_model.clear()
            if self.vision_key:
                self.vision_key.clear()
            return
        raw = next(
            (item for item in self.context.api_profile_store.load_public()["profiles"] if item.get("profile_id") == profile_id),
            {},
        )
        keys = self.context.api_profile_store.load_keys()
        self._updating = True
        if self.api_profile_name:
            self.api_profile_name.setText(str(raw.get("display_name") or ""))
        if self.api_provider:
            provider = str(raw.get("provider") or "自定义")
            if self.api_provider.findText(provider) < 0:
                self.api_provider.addItem(provider)
            self.api_provider.setCurrentText(provider)
        if self.vision_endpoint:
            self.vision_endpoint.setText(str(raw.get("api_url") or ""))
        if self.vision_model:
            self.vision_model.setText(str(raw.get("model_name") or ""))
        if self.vision_key:
            self.vision_key.setText(keys.get(profile_id, ""))
        self._updating = False

    def _apply_provider_preset(self, provider: str) -> None:
        if self._updating:
            return
        preset = PROVIDER_PRESETS.get(provider, "")
        if preset and self.vision_endpoint:
            self.vision_endpoint.setText(preset)

    def _toggle_api_key_visibility(self, visible: bool) -> None:
        """临时显示/隐藏 API Key，不写日志、不复制、不持久化明文状态。"""
        if self.vision_key:
            self.vision_key.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
            )

    def save_api_profile(self) -> None:
        name = self.api_profile_name.text().strip() if self.api_profile_name else ""
        endpoint = self.vision_endpoint.text().strip() if self.vision_endpoint else ""
        model = self.vision_model.text().strip() if self.vision_model else ""
        profile_id = str(self.api_profile_select.currentData() or "") if self.api_profile_select else ""
        if not name or not endpoint or not model:
            QMessageBox.warning(self, "无法保存", "请填写配置名称、API地址和模型。")
            return
        provider = self.api_provider.currentText() if self.api_provider else "自定义"
        if profile_id:
            profile = ApiProfile(
                profile_id=profile_id, display_name=name, provider=provider,
                api_url=endpoint, model_name=model,
            )
        else:
            profile = ApiProfile.create(
                display_name=name, provider=provider,
                api_url=endpoint, model_name=model,
            )
        stores = [self.context.api_profile_store]
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            stores.append(ApiProfileStore(pending_data_dir))
        key_text = self.vision_key.text() if self.vision_key else ""
        for store in stores:
            store.save_profile(profile, key_text)
        self._refresh_api_profiles()
        if self.api_profile_select:
            self.api_profile_select.setCurrentIndex(max(0, self.api_profile_select.findData(profile.profile_id)))
        QMessageBox.information(self, "已保存", "API配置与私钥已保存到当前数据目录。")

    def _delete_api_profile(self) -> None:
        """删除当前选中的 API 配置，含二次确认与绑定清理。"""
        if self.api_profile_select is None:
            return
        profile_id = str(self.api_profile_select.currentData() or "")
        if not profile_id:
            return
        display_name = self.api_profile_select.currentText()
        # 检查是否被视觉识图或局部文字重估使用
        visual_id = str(self.visual_binding.currentData() or "") if self.visual_binding else ""
        local_id = str(self.local_binding.currentData() or "") if self.local_binding else ""
        in_use = []
        if visual_id == profile_id:
            in_use.append("视觉识图/整体识别")
        if local_id == profile_id:
            in_use.append("局部文字重估")
        msg = f"确定永久删除配置「{display_name}」及其 API Key 吗？"
        if in_use:
            msg += f"\n\n该配置正在被以下功能使用：{', '.join(in_use)}\n删除后将清空对应绑定，需重新选择配置。"
        if not confirm_action(self, "删除配置", msg, confirm_text="删除", danger=True):
            return
        # 删除配置和 key（delete_profile 一次完成 profile/key/绑定 的真实持久化删除）
        stores = [self.context.api_profile_store]
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            stores.append(ApiProfileStore(pending_data_dir))
        for store in stores:
            store.delete_profile(profile_id)
        self._refresh_api_profiles()
        self._new_api_profile()

    # ------------------------------------------------------------------
    # 设置加载 / 保存
    # ------------------------------------------------------------------

    def load_settings(self) -> None:
        self.settings = self.context.settings_service.load()
        self._updating = True
        if self.display_name:
            self.display_name.setText(str(self.settings.get("display_name") or "用户"))
        if self.log_level:
            self.log_level.setCurrentText(str(self.settings.get("log_level") or "INFO"))
        if self.log_retention_days:
            self.log_retention_days.setValue(float(self.settings.get("log_retention_days", 30)))
        if self.log_directory:
            self.log_directory.setText(str(self.context.paths.data_dir / "logs"))
        self._refresh_api_profiles()
        self._load_forwarder_rows(self.settings.get("forwarders", []))
        self.rules_data = list(self.settings.get("profit_rules", []))
        self.refresh_rule_list()
        if self.vision_key:
            self.vision_key.setEchoMode(QLineEdit.EchoMode.Password)
        if self.btn_show_key:
            self.btn_show_key.setChecked(False)
        # 校准包版本列表随进入设置页自动加载
        self._refresh_calibration_packages()
        self._updating = False
        self.dirty = False
        self.dirtyChanged.emit(False)

    # ------------------------------------------------------------------
    # 货代管理
    # ------------------------------------------------------------------

    def _load_forwarder_rows(self, items: list[dict]) -> None:
        if self.forwarder_table is None:
            return
        self.forwarder_table.blockSignals(True)
        self.forwarder_table.setRowCount(0)
        for raw in items:
            self.add_forwarder_row(raw=raw)
        self.forwarder_table.blockSignals(False)
        self.filter_forwarders(False)

    def add_forwarder_row(self, checked: bool = False, *, raw: dict | None = None) -> None:
        del checked
        if self.forwarder_table is None:
            return
        data = raw or {
            "id": f"forwarder_{uuid4().hex}",
            "name": "新货代",
            "rate_rmb_per_kg": 0.0,
            "fixed_fee_rmb": 0.0,
            "volume_divisor": 8000.0,
            "enabled": True,
            "archived": False,
        }
        row = self.forwarder_table.rowCount()
        self.forwarder_table.insertRow(row)
        for col, value in enumerate(
            [
                str(data.get("name", "")),
                f"{float(data.get('rate_rmb_per_kg', 0)):.2f}",
                f"{float(data.get('fixed_fee_rmb', 0)):.2f}",
                f"{float(data.get('volume_divisor', 8000)):.0f}",
            ]
        ):
            item = QTableWidgetItem(value)
            if bool(data.get("archived", False)):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.forwarder_table.setItem(row, col, item)
        enabled_box = QCheckBox("启用")
        is_archived = bool(data.get("archived", False))
        enabled_box.setChecked(bool(data.get("enabled", True)) and not is_archived)
        enabled_box.setEnabled(not is_archived)
        enabled_box.toggled.connect(lambda _checked: self._mark_dirty())
        self.forwarder_table.setCellWidget(row, 4, self._center_cell(enabled_box))

        # 操作列：活动行=归档按钮，已归档行=恢复+永久删除
        identifier = str(data.get("id") or f"forwarder_{uuid4().hex}")
        self.forwarder_table.setCellWidget(row, 5, self._build_forwarder_op_widget(identifier, is_archived))
        self.forwarder_table.setItem(row, 6, QTableWidgetItem(identifier))
        self.forwarder_table.setItem(row, 7, QTableWidgetItem("1" if data.get("archived", False) else "0"))
        if raw is None:
            self._mark_dirty()

    def _find_forwarder_row(self, identifier: str) -> int:
        for row in range(self.forwarder_table.rowCount()):
            item = self.forwarder_table.item(row, 6)
            if item and item.text() == identifier:
                return row
        return -1

    def toggle_forwarder_archive(self, identifier: str) -> None:
        row = self._find_forwarder_row(identifier)
        if row < 0:
            return
        is_archived = self.forwarder_table.item(row, 7).text() == "1"
        if is_archived:
            # 恢复：无需确认
            self.forwarder_table.item(row, 7).setText("0")
            enabled_container = self.forwarder_table.cellWidget(row, 4)
            enabled_box = enabled_container.findChild(QCheckBox) if enabled_container is not None else None
            if enabled_box is not None:
                enabled_box.setChecked(True)
                enabled_box.setEnabled(True)
            for col in range(4):
                item = self.forwarder_table.item(row, col)
                if item is not None:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            # 重建操作按钮（归档）
            self.forwarder_table.setCellWidget(row, 5, self._build_forwarder_op_widget(identifier, archived=False))
        else:
            # 归档
            if not confirm_action(self, "归档货代", "归档后该货代将从当前测算与使用中列表移除，确定继续吗？"):
                return
            self.forwarder_table.item(row, 7).setText("1")
            enabled_container = self.forwarder_table.cellWidget(row, 4)
            enabled_box = enabled_container.findChild(QCheckBox) if enabled_container is not None else None
            if enabled_box is not None:
                enabled_box.setChecked(False)
                enabled_box.setEnabled(False)
            for col in range(4):
                item = self.forwarder_table.item(row, col)
                if item is not None:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # 重建操作按钮（恢复+永久删除）
            self.forwarder_table.setCellWidget(row, 5, self._build_forwarder_op_widget(identifier, archived=True))
        self._mark_dirty()
        self.filter_forwarders(self._show_archived_forwarders)

    def _delete_forwarder_permanently(self, identifier: str) -> None:
        """永久删除已归档货代。"""
        row = self._find_forwarder_row(identifier)
        if row < 0:
            return
        if self.forwarder_table.item(row, 7).text() != "1":
            QMessageBox.warning(self, "无法删除", "只能删除已归档的货代，使用中的货代请先归档。")
            return
        name = self.forwarder_table.item(row, 0).text()
        if not confirm_action(
            self,
            "永久删除",
            f"确定永久删除货代「{name}」吗？\n\n历史记录将继续使用其保存的物流快照，不会被修改。",
            confirm_text="删除",
            danger=True,
        ):
            return
        self.forwarder_table.removeRow(row)
        # 永久删除 = 立即持久化，不等待“保存货代设置”
        self._persist_forwarders_now()

    def _persist_forwarders_now(self) -> bool:
        """把当前表格的完整货代列表立即写入 settings.json。

        用于：永久删除后的立即落盘、普通“保存货代设置”。
        若 selected_forwarder_id 失效则重选第一个启用货代或清空。
        """
        try:
            forwarders = self.collect_forwarders()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return False
        latest = self.context.settings_service.load()
        enabled_ids = [item["id"] for item in forwarders if item["enabled"] and not item["archived"]]
        selected = latest.get("selected_forwarder_id")
        if selected not in enabled_ids:
            selected = enabled_ids[0] if enabled_ids else ""
        latest["forwarders"] = forwarders
        latest["selected_forwarder_id"] = selected
        self.context.settings_service.save(latest)
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            SettingsService.save_copy(latest, pending_data_dir / "settings.json")
        self.settings = latest
        self.forwardersSaved.emit()
        self._update_forwarder_counts()
        return True

    def filter_forwarders(self, archived: bool) -> None:
        self._show_archived_forwarders = archived
        if self.show_active:
            self.show_active.setChecked(not archived)
        if self.show_archived:
            self.show_archived.setChecked(archived)
        for row in range(self.forwarder_table.rowCount()):
            is_archived = self.forwarder_table.item(row, 7).text() == "1"
            self.forwarder_table.setRowHidden(row, is_archived != archived)
        self._update_forwarder_counts()

    def _update_forwarder_counts(self) -> None:
        """实时统计使用中 / 已归档货代数并更新按钮文本。"""
        active_count = 0
        archived_count = 0
        for row in range(self.forwarder_table.rowCount()):
            if self.forwarder_table.item(row, 7).text() == "1":
                archived_count += 1
            else:
                active_count += 1
        if self.show_active:
            self.show_active.setText(f"使用中的货代({active_count})")
        if self.show_archived:
            self.show_archived.setText(f"已归档({archived_count})")

    def collect_forwarders(self) -> list[dict]:
        output = []
        for row in range(self.forwarder_table.rowCount()):
            enabled_container = self.forwarder_table.cellWidget(row, 4)
            enabled_box = enabled_container.findChild(QCheckBox) if enabled_container is not None else None
            archived = self.forwarder_table.item(row, 7).text() == "1"
            try:
                forwarder = Forwarder(
                    id=self.forwarder_table.item(row, 6).text().strip(),
                    name=self.forwarder_table.item(row, 0).text().strip(),
                    rate_rmb_per_kg=float(self.forwarder_table.item(row, 1).text()),
                    fixed_fee_rmb=float(self.forwarder_table.item(row, 2).text()),
                    volume_divisor=float(self.forwarder_table.item(row, 3).text()),
                    enabled=isinstance(enabled_box, QCheckBox) and enabled_box.isChecked() and not archived,
                    archived=archived,
                )
                forwarder.validate()
            except Exception as exc:
                raise ValueError(f"第 {row + 1} 行货代数据无效：{exc}") from exc
            output.append(asdict(forwarder))
        return output

    def save_forwarders_only(self) -> None:
        if not self._persist_forwarders_now():
            return
        self.dirty = False
        self.dirtyChanged.emit(False)
        QMessageBox.information(self, "已保存", "货代设置已保存。")

    # ------------------------------------------------------------------
    # 利润规则
    # ------------------------------------------------------------------

    def refresh_rule_list(self) -> None:
        if self.rule_list is None:
            return
        current_source = self.current_rule_source_index()
        self.rule_list.clear()
        self.visible_rule_indices = []
        for index, rule in enumerate(self.rules_data):
            if rule.get("archived"):
                continue
            self.visible_rule_indices.append(index)
            enabled = bool(rule.get("enabled", True))
            status = "启用" if enabled else "停用"
            item = QListWidgetItem(f"{rule.get('name', '未命名规则')}\n{status}")
            item.setForeground(QColor("#219B68" if enabled else "#7E8999"))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self.rule_list.addItem(item)
        if self.visible_rule_indices:
            target = self.visible_rule_indices.index(current_source) if current_source in self.visible_rule_indices else 0
            self.rule_list.setCurrentRow(target)

    def current_rule_source_index(self) -> int:
        item = self.rule_list.currentItem() if self.rule_list is not None else None
        if item is None:
            return -1
        value = item.data(Qt.ItemDataRole.UserRole)
        return int(value) if value is not None else -1

    def add_rule(self) -> None:
        self.rules_data.append(
            {
                "id": f"rule_{uuid4().hex}",
                "name": "新规则",
                "condition_field": "sale_price_usd",
                "compare_op": "lt",
                "condition_value": 0.0,
                "direction": "income",
                "adjustment_type": "fixed",
                "adjustment_value": 0.0,
                "currency": "USD",
                "percent_base": None,
                "enabled": False,
                "archived": False,
                "description": "",
            }
        )
        self.refresh_rule_list()
        self.rule_list.setCurrentRow(self.rule_list.count() - 1)
        self._mark_dirty()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def load_rule_editor(self, visible_row: int) -> None:
        if visible_row < 0 or visible_row >= len(self.visible_rule_indices):
            return
        raw = self.rules_data[self.visible_rule_indices[visible_row]]
        self._updating = True
        if self.rule_name:
            self.rule_name.setText(str(raw.get("name") or ""))
        self._set_combo_data(self.rule_condition_field, raw.get("condition_field"))
        self._set_combo_data(self.rule_compare, raw.get("compare_op"))
        if self.rule_condition_value:
            self.rule_condition_value.setValue(float(raw.get("condition_value", 0)))
        self._set_combo_data(self.rule_direction, raw.get("direction"))
        self._set_combo_data(self.rule_type, raw.get("adjustment_type"))
        if self.rule_value:
            self.rule_value.setValue(float(raw.get("adjustment_value", 0)))
        if self.rule_currency:
            self.rule_currency.setCurrentText(str(raw.get("currency") or "RMB"))
        self._set_combo_data(self.rule_percent_base, raw.get("percent_base"))
        if self.btn_disable_rule:
            self.btn_disable_rule.setChecked(bool(raw.get("enabled", True)))
        if self.rule_description:
            self.rule_description.setPlainText(str(raw.get("description") or ""))
        self._updating = False
        if self.btn_disable_rule:
            self._update_rule_toggle_text(self.btn_disable_rule.isChecked())

    def _update_rule_toggle_text(self, checked: bool) -> None:
        if self.btn_disable_rule is None:
            return
        self.btn_disable_rule.setText("✓ 已启用" if checked else "停用")
        self.btn_disable_rule.setStyleSheet(
            "color:#219B68;font-weight:600;" if checked else "color:#7E8999;"
        )

    def save_current_rule(self) -> None:
        row = self.current_rule_source_index()
        if row < 0:
            return
        rule = AdjustmentRule(
            id=str(self.rules_data[row].get("id") or f"rule_{uuid4().hex}"),
            name=self.rule_name.text().strip(),
            condition_field=str(self.rule_condition_field.currentData()),
            compare_op=CompareOp(str(self.rule_compare.currentData())),
            condition_value=float(self.rule_condition_value.value()),
            direction=AdjustmentDirection(str(self.rule_direction.currentData())),
            adjustment_type=AdjustmentType(str(self.rule_type.currentData())),
            adjustment_value=float(self.rule_value.value()),
            currency=self.rule_currency.currentText(),
            percent_base=self.rule_percent_base.currentData(),
            enabled=self.btn_disable_rule.isChecked(),
            archived=False,
            description=self.rule_description.toPlainText().strip(),
        )
        try:
            rule.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "规则无效", str(exc))
            return
        self.rules_data[row] = SettingsService.rule_to_dict(rule)
        # 保存规则 = 立即持久化，不等待总“保存设置”
        self._persist_rules_now()

    def archive_current_rule(self) -> None:
        row = self.current_rule_source_index()
        if row < 0:
            return
        if not confirm_action(self, "归档规则", "归档后该规则将从当前列表和主界面利润规则中移除，确定继续吗？"):
            return
        self.rules_data[row]["archived"] = True
        self.rules_data[row]["enabled"] = False
        if self.settings.get("selected_profit_rule_id") == self.rules_data[row].get("id"):
            self.settings["selected_profit_rule_id"] = ""
        # 归档规则 = 立即持久化，与 delete 语义一致
        self._persist_rules_now()

    def delete_current_rule(self) -> None:
        row = self.current_rule_source_index()
        if row < 0:
            return
        if not confirm_action(self, "删除规则", "确定永久删除当前规则吗？", confirm_text="删除", danger=True):
            return
        deleted_id = self.rules_data[row].get("id")
        del self.rules_data[row]
        # 删除的是当前主页面选中的规则：重选一个启用规则或清空
        if self.settings.get("selected_profit_rule_id") == deleted_id:
            enabled = [
                item for item in self.rules_data
                if item.get("enabled", True) and not item.get("archived", False)
            ]
            self.settings["selected_profit_rule_id"] = enabled[0].get("id", "") if enabled else ""
        # 删除 = 立即持久化，不等待总“保存设置”
        self._persist_rules_now()

    def _persist_rules_now(self) -> None:
        """把当前 rules_data 立即写入 settings.json 并同步主页面。

        若 selected_profit_rule_id 失效则重选第一个启用规则或清空。
        """
        latest = self.context.settings_service.load()
        enabled_rule_ids = [
            str(item.get("id"))
            for item in self.rules_data
            if item.get("enabled", True) and not item.get("archived", False)
        ]
        selected_rule = str(latest.get("selected_profit_rule_id") or "")
        if selected_rule not in enabled_rule_ids:
            selected_rule = enabled_rule_ids[0] if enabled_rule_ids else ""
        latest["profit_rules"] = self.rules_data
        latest["selected_profit_rule_id"] = selected_rule
        self.context.settings_service.save(latest)
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            SettingsService.save_copy(latest, pending_data_dir / "settings.json")
        self.settings = latest
        self.refresh_rule_list()
        # 最窄刷新机制：主页面货代卡与利润规则下拉立即同步，不改动脏状态
        self.forwardersSaved.emit()

    # ------------------------------------------------------------------
    # 保存全部设置
    # ------------------------------------------------------------------

    def save_settings(self) -> None:
        latest = self.context.settings_service.load()

        # 验证显示名称：去除首尾空格后 Unicode 可见字符 1-8 个
        if self.display_name:
            raw_name = self.display_name.text().strip()
            visible_len = sum(1 for ch in raw_name if not ch.isspace())
            if visible_len > 8:
                QMessageBox.warning(
                    self, "名称过长",
                    f"显示名称最多 8 个字符，当前共 {visible_len} 个字符。\n请缩短后保存。",
                )
                return
            display_name_val = raw_name if visible_len >= 1 else "用户"
        else:
            display_name_val = "用户"

        if self.log_level:
            latest["log_level"] = self.log_level.currentText()
        if self.log_retention_days:
            latest["log_retention_days"] = int(self.log_retention_days.value())
        latest["display_name"] = display_name_val

        # 货代和利润规则分别由其专用保存/增删操作即时持久化。全局保存是
        # API binding 与通用设置的入口，不得把页面中的空白或旧副本写回，
        # 因而始终保留 SettingsService 刚读取到的四项业务设置。
        # New API settings live in the selected data directory's separate
        # profile/key files.  Do not copy a secret back into settings.json.
        latest.pop("vision_api_key", None)
        self.settings = latest
        self.context.settings_service.save(self.settings)
        # A directory switch applies after restart.  Until then this page is
        # backed by the old directory, so mirror subsequent API/config saves to
        # the already-selected directory as well.
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            SettingsService.save_copy(self.settings, pending_data_dir / "settings.json")
        # Persist visual/local binding selections to ApiProfileStore.
        visual_id = str(self.visual_binding.currentData() or "") if self.visual_binding else ""
        local_id = str(self.local_binding.currentData() or "") if self.local_binding else ""
        binding_stores = [self.context.api_profile_store]
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            binding_stores.append(ApiProfileStore(pending_data_dir))
        for store in binding_stores:
            store.bind(VISUAL_AI, visual_id or None)
            store.bind(LOCAL_REESTIMATE, local_id or None)
        self.dirty = False
        self.dirtyChanged.emit(False)
        self.settingsSaved.emit()
        QMessageBox.information(self, "已保存", "设置已保存到本地。")
