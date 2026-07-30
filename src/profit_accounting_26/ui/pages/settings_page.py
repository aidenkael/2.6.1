from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
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
from profit_accounting_26.ui.widgets import Card, QuickLineEdit, SectionHeader


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

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(8)
        self._build_basic()
        self._build_forwarders()
        self._build_rules()
        self._build_actions()
        self.load_settings()

    def _mark_dirty(self) -> None:
        if self._updating:
            return
        if not self.dirty:
            self.dirty = True
            self.dirtyChanged.emit(True)

    def _build_basic(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(6)
        layout.addWidget(SectionHeader("基础设置"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.display_name = QuickLineEdit()
        self.display_name.setMaximumWidth(300)
        self.vision_endpoint = QuickLineEdit()
        self.vision_endpoint.setPlaceholderText("例如：https://api.openai.com/v1")
        self.vision_model = QuickLineEdit()
        self.vision_model.setPlaceholderText("支持图片的模型名称")
        self.vision_key = QuickLineEdit()
        self.vision_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.vision_key.setPlaceholderText("API Key，仅保存在本机设置文件")
        self.api_profile_select = QComboBox()
        self.api_profile_name = QuickLineEdit()
        self.api_profile_name.setPlaceholderText("配置名称")
        self.api_provider = QComboBox()
        self.api_provider.addItems(PROVIDER_PRESETS.keys())
        self.visual_binding = QComboBox()
        self.local_binding = QComboBox()
        self.save_api_profile_button = QPushButton("保存 API 配置")
        self.save_api_profile_button.setProperty("primary", True)
        self.save_api_profile_button.clicked.connect(self.save_api_profile)
        self.api_profile_select.currentIndexChanged.connect(self._load_selected_api_profile)
        self.api_provider.currentTextChanged.connect(self._apply_provider_preset)
        fields = [
            ("展示名称", self.display_name),
            ("AI API地址", self.vision_endpoint),
            ("AI模型", self.vision_model),
            ("AI API Key", self.vision_key),
        ]
        for index, (label_text, widget) in enumerate(fields):
            box = QWidget()
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(0, 0, 0, 0)
            box_layout.setSpacing(3)
            label = QLabel(label_text)
            label.setProperty("muted", True)
            box_layout.addWidget(label)
            box_layout.addWidget(widget)
            grid.addWidget(box, 0, index)
        grid.setColumnStretch(1, 2)
        layout.addLayout(grid)
        api_row = QHBoxLayout()
        api_row.setSpacing(7)
        for widget in (
            QLabel("API配置"), self.api_profile_select, self.api_profile_name, self.api_provider,
            QLabel("视觉/整体"), self.visual_binding, QLabel("局部文字"), self.local_binding,
            self.save_api_profile_button,
        ):
            api_row.addWidget(widget)
        layout.addLayout(api_row)
        self.content_layout.addWidget(card)
        for widget in (self.display_name, self.vision_endpoint, self.vision_model, self.vision_key):
            widget.textChanged.connect(lambda _text: self._mark_dirty())
        self.visual_binding.currentIndexChanged.connect(lambda _index: self._mark_dirty())
        self.local_binding.currentIndexChanged.connect(lambda _index: self._mark_dirty())

    def _build_forwarders(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(6)
        header = SectionHeader("货代管理")
        self.show_active = QPushButton("使用中的货代")
        self.show_active.setCheckable(True)
        self.show_active.setChecked(True)
        self.show_archived = QPushButton("已归档")
        self.show_archived.setCheckable(True)
        add = QPushButton("新增货代")
        save = QPushButton("保存货代设置")
        save.setProperty("primary", True)
        self.show_active.clicked.connect(lambda: self.filter_forwarders(False))
        self.show_archived.clicked.connect(lambda: self.filter_forwarders(True))
        add.clicked.connect(self.add_forwarder_row)
        save.clicked.connect(self.save_forwarders_only)
        for widget in (self.show_active, self.show_archived, add, save):
            header.right_layout.addWidget(widget)
        layout.addWidget(header)
        self.forwarder_table = QTableWidget(0, 8)
        self.forwarder_table.setHorizontalHeaderLabels(
            ["名称", "头程单价（RMB/kg）", "固定服务费（RMB）", "体积重除数", "启用状态", "操作", "内部ID", "归档"]
        )
        self.forwarder_table.setAlternatingRowColors(True)
        self.forwarder_table.verticalHeader().setVisible(False)
        self.forwarder_table.horizontalHeader().setStretchLastSection(False)
        from PySide6.QtWidgets import QHeaderView
        self.forwarder_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            self.forwarder_table.setColumnWidth(col, 160)
        self.forwarder_table.setColumnWidth(4, 110)
        self.forwarder_table.setColumnWidth(5, 100)
        self.forwarder_table.setColumnHidden(6, True)
        self.forwarder_table.setColumnHidden(7, True)
        self.forwarder_table.setFixedHeight(190)
        self.forwarder_table.itemChanged.connect(lambda _item: self._mark_dirty())
        layout.addWidget(self.forwarder_table)
        self.content_layout.addWidget(card)

    def _build_rules(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(6)
        header = SectionHeader("利润调整规则")
        add = QPushButton("新增规则")
        add.clicked.connect(self.add_rule)
        header.right_layout.addWidget(add)
        layout.addWidget(header)
        body = QHBoxLayout()
        body.setSpacing(8)
        self.rule_list = QListWidget()
        self.rule_list.setMinimumWidth(300)
        self.rule_list.setMaximumWidth(390)
        self.rule_list.currentRowChanged.connect(self.load_rule_editor)
        body.addWidget(self.rule_list, 1)

        editor = Card(soft=True)
        form = QGridLayout(editor)
        form.setContentsMargins(9, 8, 9, 8)
        form.setHorizontalSpacing(7)
        form.setVerticalSpacing(5)
        self.rule_name = QuickLineEdit()
        self.rule_condition_field = QComboBox()
        self.rule_condition_field.addItem("最终售价（美元）", "sale_price_usd")
        self.rule_condition_field.addItem("最终售价（人民币）", "sale_price_rmb")
        self.rule_compare = QComboBox()
        for text, value in (("小于", "lt"), ("小于等于", "lte"), ("大于", "gt"), ("大于等于", "gte"), ("等于", "eq")):
            self.rule_compare.addItem(text, value)
        self.rule_condition_value = QDoubleSpinBox()
        self.rule_condition_value.setRange(0, 1_000_000)
        self.rule_condition_value.setDecimals(4)
        self.rule_condition_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.rule_direction = QComboBox()
        self.rule_direction.addItem("增加收入", "income")
        self.rule_direction.addItem("增加成本", "cost")
        self.rule_type = QComboBox()
        self.rule_type.addItem("固定金额", "fixed")
        self.rule_type.addItem("百分比", "percent")
        self.rule_value = QDoubleSpinBox()
        self.rule_value.setRange(0, 1_000_000)
        self.rule_value.setDecimals(4)
        self.rule_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.rule_currency = QComboBox()
        self.rule_currency.addItems(["USD", "RMB"])
        self.rule_percent_base = QComboBox()
        self.rule_percent_base.addItem("不适用", None)
        self.rule_percent_base.addItem("最终售价人民币", "sale_price_rmb")
        self.rule_percent_base.addItem("预留后收入", "revenue_after_reserve_rmb")
        self.rule_percent_base.addItem("计算采用总成本", "total_cost_rmb")
        self.rule_description = QTextEdit()
        self.rule_description.setFixedHeight(54)

        fields = [
            ("规则名称", self.rule_name),
            ("条件字段", self.rule_condition_field),
            ("比较方式", self.rule_compare),
            ("条件值", self.rule_condition_value),
            ("调整方向", self.rule_direction),
            ("调整类型", self.rule_type),
            ("调整值", self.rule_value),
            ("币种", self.rule_currency),
            ("百分比基数", self.rule_percent_base),
        ]
        for index, (label_text, widget) in enumerate(fields):
            row = (index // 3) * 2
            col = index % 3
            label = QLabel(label_text)
            label.setProperty("muted", True)
            form.addWidget(label, row, col)
            form.addWidget(widget, row + 1, col)
        form.addWidget(QLabel("说明"), 6, 0)
        form.addWidget(self.rule_description, 7, 0, 1, 3)

        action_row = QHBoxLayout()
        self.rule_enabled_toggle = QPushButton("停用")
        self.rule_enabled_toggle.setCheckable(True)
        self.rule_enabled_toggle.toggled.connect(self._update_rule_toggle_text)
        save_rule = QPushButton("保存规则")
        save_rule.setProperty("primary", True)
        archive_rule = QPushButton("归档")
        delete_rule = QPushButton("删除")
        delete_rule.setProperty("danger", True)
        save_rule.clicked.connect(self.save_current_rule)
        archive_rule.clicked.connect(self.archive_current_rule)
        delete_rule.clicked.connect(self.delete_current_rule)
        for widget in (self.rule_enabled_toggle, save_rule, archive_rule, delete_rule):
            action_row.addWidget(widget)
        action_row.addStretch(1)
        form.addLayout(action_row, 8, 0, 1, 3)
        body.addWidget(editor, 3)
        layout.addLayout(body)
        self.content_layout.addWidget(card, 1)

    def _build_actions(self) -> None:
        card = Card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.addStretch(1)
        save = QPushButton("保存设置")
        save.setProperty("primary", True)
        discard = QPushButton("放弃修改")
        save.clicked.connect(self.save_settings)
        discard.clicked.connect(self.load_settings)
        layout.addWidget(save)
        layout.addSpacing(10)
        layout.addWidget(discard)
        layout.addStretch(1)
        self.content_layout.addWidget(card)

    def _refresh_api_profiles(self) -> None:
        public = self.context.api_profile_store.load_public()
        profiles = [item for item in public["profiles"] if isinstance(item, dict)]
        bindings = public["button_bindings"]
        for combo in (self.api_profile_select, self.visual_binding, self.local_binding):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("新建配置", "")
            for item in profiles:
                combo.addItem(str(item.get("display_name") or "未命名配置"), str(item.get("profile_id") or ""))
            combo.blockSignals(False)
        self.visual_binding.setCurrentIndex(max(0, self.visual_binding.findData(bindings.get(VISUAL_AI))))
        self.local_binding.setCurrentIndex(max(0, self.local_binding.findData(bindings.get(LOCAL_REESTIMATE))))

    def _load_selected_api_profile(self, _index: int) -> None:
        profile_id = str(self.api_profile_select.currentData() or "")
        if not profile_id:
            self.api_profile_name.clear()
            self.api_provider.setCurrentText("自定义")
            self.vision_endpoint.clear()
            self.vision_model.clear()
            self.vision_key.clear()
            return
        raw = next(
            (item for item in self.context.api_profile_store.load_public()["profiles"] if item.get("profile_id") == profile_id),
            {},
        )
        keys = self.context.api_profile_store.load_keys()
        self._updating = True
        self.api_profile_name.setText(str(raw.get("display_name") or ""))
        self.api_provider.setCurrentText(str(raw.get("provider") or "自定义"))
        self.vision_endpoint.setText(str(raw.get("api_url") or ""))
        self.vision_model.setText(str(raw.get("model_name") or ""))
        self.vision_key.setText(keys.get(profile_id, ""))
        self._updating = False

    def _apply_provider_preset(self, provider: str) -> None:
        if self._updating:
            return
        preset = PROVIDER_PRESETS.get(provider, "")
        if preset:
            self.vision_endpoint.setText(preset)

    def save_api_profile(self) -> None:
        profile_id = str(self.api_profile_select.currentData() or "")
        name = self.api_profile_name.text().strip()
        if not name or not self.vision_endpoint.text().strip() or not self.vision_model.text().strip():
            QMessageBox.warning(self, "无法保存", "请填写配置名称、API地址和模型。")
            return
        if profile_id:
            profile = ApiProfile(
                profile_id=profile_id, display_name=name, provider=self.api_provider.currentText(),
                api_url=self.vision_endpoint.text().strip(), model_name=self.vision_model.text().strip(),
            )
        else:
            profile = ApiProfile.create(
                display_name=name, provider=self.api_provider.currentText(),
                api_url=self.vision_endpoint.text().strip(), model_name=self.vision_model.text().strip(),
            )
        stores = [self.context.api_profile_store]
        pending_data_dir = ApplicationPaths.configured_data_dir()
        if pending_data_dir is not None and pending_data_dir.resolve() != self.context.paths.data_dir.resolve():
            stores.append(ApiProfileStore(pending_data_dir))
        visual_id = str(self.visual_binding.currentData() or profile.profile_id)
        local_id = str(self.local_binding.currentData() or profile.profile_id)
        for store in stores:
            store.save_profile(profile, self.vision_key.text())
            store.bind(VISUAL_AI, visual_id)
            store.bind(LOCAL_REESTIMATE, local_id)
        self._refresh_api_profiles()
        self.api_profile_select.setCurrentIndex(max(0, self.api_profile_select.findData(profile.profile_id)))
        QMessageBox.information(self, "已保存", "API配置与私钥已保存到当前数据目录。")

    def load_settings(self) -> None:
        self.settings = self.context.settings_service.load()
        self._updating = True
        self.display_name.setText(str(self.settings.get("display_name") or "用户"))
        self.vision_endpoint.setText(str(self.settings.get("vision_api_endpoint") or ""))
        self.vision_model.setText(str(self.settings.get("vision_api_model") or ""))
        self.vision_key.setText(str(self.settings.get("vision_api_key") or ""))
        self._refresh_api_profiles()
        self._load_forwarder_rows(self.settings.get("forwarders", []))
        self.rules_data = list(self.settings.get("profit_rules", []))
        self.refresh_rule_list()
        self._updating = False
        self.dirty = False
        self.dirtyChanged.emit(False)

    def _load_forwarder_rows(self, items: list[dict]) -> None:
        self.forwarder_table.blockSignals(True)
        self.forwarder_table.setRowCount(0)
        for raw in items:
            self.add_forwarder_row(raw=raw)
        self.forwarder_table.blockSignals(False)
        self.filter_forwarders(False)

    def add_forwarder_row(self, checked: bool = False, *, raw: dict | None = None) -> None:
        del checked
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
        self.show_active.setChecked(not archived)
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

    def _merge_forwarders_into_settings(self) -> list[dict]:
        forwarders = self.collect_forwarders()
        enabled_ids = [item["id"] for item in forwarders if item["enabled"] and not item["archived"]]
        selected = self.settings.get("selected_forwarder_id")
        if selected not in enabled_ids:
            selected = enabled_ids[0] if enabled_ids else ""
        self.settings["forwarders"] = forwarders
        self.settings["selected_forwarder_id"] = selected
        return forwarders

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

    def refresh_rule_list(self) -> None:
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
        item = self.rule_list.currentItem() if hasattr(self, "rule_list") else None
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
        self.rule_name.setText(str(raw.get("name") or ""))
        self._set_combo_data(self.rule_condition_field, raw.get("condition_field"))
        self._set_combo_data(self.rule_compare, raw.get("compare_op"))
        self.rule_condition_value.setValue(float(raw.get("condition_value", 0)))
        self._set_combo_data(self.rule_direction, raw.get("direction"))
        self._set_combo_data(self.rule_type, raw.get("adjustment_type"))
        self.rule_value.setValue(float(raw.get("adjustment_value", 0)))
        self.rule_currency.setCurrentText(str(raw.get("currency") or "RMB"))
        self._set_combo_data(self.rule_percent_base, raw.get("percent_base"))
        self.rule_enabled_toggle.setChecked(bool(raw.get("enabled", True)))
        self.rule_description.setPlainText(str(raw.get("description") or ""))
        self._updating = False
        self._update_rule_toggle_text(self.rule_enabled_toggle.isChecked())

    def _update_rule_toggle_text(self, checked: bool) -> None:
        self.rule_enabled_toggle.setText("✓ 已启用" if checked else "停用")
        self.rule_enabled_toggle.setStyleSheet(
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
            enabled=self.rule_enabled_toggle.isChecked(),
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

    def save_settings(self) -> None:
        try:
            forwarders = self.collect_forwarders()
        except ValueError as exc:
            QMessageBox.warning(self, "无法保存", str(exc))
            return
        latest = self.context.settings_service.load()
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
                "display_name": self.display_name.text().strip() or "用户",
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
