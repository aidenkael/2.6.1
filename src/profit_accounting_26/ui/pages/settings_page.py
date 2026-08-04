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
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
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

    def _hide_preview_controls(self) -> None:
        """契约 §13.2：隐藏 Designer 预览行与无真实业务的测试/删除按钮。"""
        for name in ("btnTestApi1", "btnDeleteApi1"):
            widget = self._root.findChild(QWidget, name)
            if widget:
                widget.setVisible(False)
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
        self.forwarder_table.setColumnWidth(4, 110)
        self.forwarder_table.setColumnWidth(5, 100)
        self.forwarder_table.setColumnHidden(6, True)
        self.forwarder_table.setColumnHidden(7, True)

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
    # API Profile
    # ------------------------------------------------------------------

    def _refresh_api_profiles(self) -> None:
        public = self.context.api_profile_store.load_public()
        profiles = [item for item in public["profiles"] if isinstance(item, dict)]
        bindings = public["button_bindings"]
        for combo in (self.api_profile_select, self.visual_binding, self.local_binding):
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("新建配置", "")
            for item in profiles:
                combo.addItem(str(item.get("display_name") or "未命名配置"), str(item.get("profile_id") or ""))
            combo.blockSignals(False)
        if self.visual_binding:
            self.visual_binding.setCurrentIndex(max(0, self.visual_binding.findData(bindings.get(VISUAL_AI))))
        if self.local_binding:
            self.local_binding.setCurrentIndex(max(0, self.local_binding.findData(bindings.get(LOCAL_REESTIMATE))))

    def _new_api_profile(self) -> None:
        if self.api_profile_select:
            self.api_profile_select.setCurrentIndex(max(0, self.api_profile_select.findData("")))

    def _load_selected_api_profile(self, _index: int) -> None:
        if self.api_profile_select is None:
            return
        profile_id = str(self.api_profile_select.currentData() or "")
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
        visual_id = str(self.visual_binding.currentData() or profile.profile_id) if self.visual_binding else profile.profile_id
        local_id = str(self.local_binding.currentData() or profile.profile_id) if self.local_binding else profile.profile_id
        key_text = self.vision_key.text() if self.vision_key else ""
        for store in stores:
            store.save_profile(profile, key_text)
            store.bind(VISUAL_AI, visual_id)
            store.bind(LOCAL_REESTIMATE, local_id)
        self._refresh_api_profiles()
        if self.api_profile_select:
            self.api_profile_select.setCurrentIndex(max(0, self.api_profile_select.findData(profile.profile_id)))
        QMessageBox.information(self, "已保存", "API配置与私钥已保存到当前数据目录。")

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
        self.forwarder_table.setCellWidget(row, 4, enabled_box)
        operation = QPushButton("已归档" if data.get("archived", False) else "归档")
        identifier = str(data.get("id") or f"forwarder_{uuid4().hex}")
        operation.clicked.connect(lambda _checked=False, fid=identifier: self.toggle_forwarder_archive(fid))
        operation.setEnabled(not bool(data.get("archived", False)))
        self.forwarder_table.setCellWidget(row, 5, operation)
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
        if self.forwarder_table.item(row, 7).text() == "1":
            return
        answer = QMessageBox.question(
            self,
            "归档货代",
            "归档后该货代将从当前测算与使用中列表移除，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.forwarder_table.item(row, 7).setText("1")
        enabled_box = self.forwarder_table.cellWidget(row, 4)
        if isinstance(enabled_box, QCheckBox):
            enabled_box.setChecked(False)
            enabled_box.setEnabled(False)
        operation = self.forwarder_table.cellWidget(row, 5)
        if isinstance(operation, QPushButton):
            operation.setText("已归档")
            operation.setEnabled(False)
        for col in range(4):
            item = self.forwarder_table.item(row, col)
            if item is not None:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._mark_dirty()
        self.filter_forwarders(self._show_archived_forwarders)

    def filter_forwarders(self, archived: bool) -> None:
        self._show_archived_forwarders = archived
        if self.show_active:
            self.show_active.setChecked(not archived)
        if self.show_archived:
            self.show_archived.setChecked(archived)
        for row in range(self.forwarder_table.rowCount()):
            is_archived = self.forwarder_table.item(row, 7).text() == "1"
            self.forwarder_table.setRowHidden(row, is_archived != archived)

    def collect_forwarders(self) -> list[dict]:
        output = []
        for row in range(self.forwarder_table.rowCount()):
            enabled_box = self.forwarder_table.cellWidget(row, 4)
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
        try:
            forwarders = self.collect_forwarders()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        latest = self.context.settings_service.load()
        enabled_ids = [item["id"] for item in forwarders if item["enabled"] and not item["archived"]]
        selected = latest.get("selected_forwarder_id")
        if selected not in enabled_ids:
            selected = enabled_ids[0] if enabled_ids else ""
        latest["forwarders"] = forwarders
        latest["selected_forwarder_id"] = selected
        self.context.settings_service.save(latest)
        self.settings.update({"forwarders": forwarders, "selected_forwarder_id": selected})
        self.forwardersSaved.emit()
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
        self.refresh_rule_list()
        self._mark_dirty()

    def archive_current_rule(self) -> None:
        row = self.current_rule_source_index()
        if row < 0:
            return
        answer = QMessageBox.question(
            self,
            "归档规则",
            "归档后该规则将从当前列表和主界面利润规则中移除，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.rules_data[row]["archived"] = True
        self.rules_data[row]["enabled"] = False
        if self.settings.get("selected_profit_rule_id") == self.rules_data[row].get("id"):
            self.settings["selected_profit_rule_id"] = ""
        self.refresh_rule_list()
        self._mark_dirty()

    def delete_current_rule(self) -> None:
        row = self.current_rule_source_index()
        if row < 0:
            return
        answer = QMessageBox.question(
            self,
            "删除规则",
            "确定永久删除当前规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        deleted_id = self.rules_data[row].get("id")
        del self.rules_data[row]
        if self.settings.get("selected_profit_rule_id") == deleted_id:
            self.settings["selected_profit_rule_id"] = ""
        self.refresh_rule_list()
        self._mark_dirty()

    # ------------------------------------------------------------------
    # 保存全部设置
    # ------------------------------------------------------------------

    def save_settings(self) -> None:
        try:
            forwarders = self.collect_forwarders()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        latest = self.context.settings_service.load()
        if self.log_level:
            latest["log_level"] = self.log_level.currentText()
        if self.log_retention_days:
            latest["log_retention_days"] = int(self.log_retention_days.value())
        enabled_ids = [item["id"] for item in forwarders if item["enabled"] and not item["archived"]]
        selected_forwarder = latest.get("selected_forwarder_id")
        if selected_forwarder not in enabled_ids:
            selected_forwarder = enabled_ids[0] if enabled_ids else ""
        enabled_rule_ids = [
            str(item.get("id"))
            for item in self.rules_data
            if item.get("enabled", True) and not item.get("archived", False)
        ]
        selected_rule = str(latest.get("selected_profit_rule_id") or "")
        if selected_rule not in enabled_rule_ids:
            selected_rule = enabled_rule_ids[0] if enabled_rule_ids else ""
        latest.update(
            {
                "display_name": (self.display_name.text().strip() or "用户") if self.display_name else "用户",
                "forwarders": forwarders,
                "selected_forwarder_id": selected_forwarder,
                "profit_rules": self.rules_data,
                "selected_profit_rule_id": selected_rule,
            }
        )
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
        self.dirty = False
        self.dirtyChanged.emit(False)
        self.settingsSaved.emit()
        QMessageBox.information(self, "已保存", "设置已保存到本地。")
