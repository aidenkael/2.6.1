from __future__ import annotations

import hashlib
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext, CalculationService, ImageSession
from profit_accounting_26.application.recognition_service import (
    RecognitionCancellation,
    RecognitionCancelledError,
    RecognitionResponseError,
    RecognitionUnavailableError,
)
from profit_accounting_26.domain.models import (
    AIObservation,
    ImageType,
    PackagingProposal,
    PackagingScenario,
)
from profit_accounting_26.domain.rules import evaluate_rule
from profit_accounting_26.ui.widgets import (
    Card,
    ImageSlotWidget,
    LabeledSpin,
    QuickLineEdit,
    QuoteCard,
    SectionHeader,
)


class RecognitionWorker(QObject):
    completed = Signal(object, object)
    failed = Signal(str, str)

    def __init__(self, service, image_items: list[dict[str, str]], cancellation: RecognitionCancellation) -> None:
        super().__init__()
        self._service = service
        self._image_items = image_items
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            observation, proposal = self._service.recognize(
                self._image_items,
                cancellation=self._cancellation,
            )
        except RecognitionCancelledError as exc:
            self.failed.emit("cancelled", str(exc))
        except RecognitionUnavailableError as exc:
            self.failed.emit("unavailable", str(exc))
        except RecognitionResponseError as exc:
            self.failed.emit("response", str(exc))
        except Exception as exc:
            self.failed.emit("failed", str(exc))
        else:
            self.completed.emit(observation, proposal)


class CalculationPage(QWidget):
    dirtyChanged = Signal(bool)
    saved = Signal(str)

    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self.calculation_service = CalculationService()
        self.settings = context.settings_service.load()
        self.observation = AIObservation()
        self.proposal: PackagingProposal | None = None
        self.record_id: str | None = None
        self.dirty = False
        self.packaging_stale = False
        self._updating = False
        self.image_slots: list[ImageSlotWidget] = []
        self.quote_cards: dict[str, QuoteCard] = {}
        self.current_quote = None
        self.current_forwarder = None
        self.current_system_cost: float | None = None
        self.selected_forwarder_id = str(self.settings.get("selected_forwarder_id") or "")
        self.selected_profit_rule_id = str(self.settings.get("selected_profit_rule_id") or "")
        self.forwarder_selection_changed = False
        self.package_selection_changed = False
        self.manual_scenarios: set[str] = set()
        self._recognition_thread: QThread | None = None
        self._recognition_worker: RecognitionWorker | None = None
        self._recognition_cancellation: RecognitionCancellation | None = None
        self._recognition_dialog: QDialog | None = None

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(12, 10, 12, 12)
        self.content_layout.setSpacing(8)

        self._build_image_section()
        self._build_ai_section()
        self._build_cost_section()
        self._build_profit_section()
        self._build_bottom_actions()
        self._connect_calculation_signals()
        self.rebuild_image_slots(int(self.settings.get("image_slot_count", 5)))
        self.rebuild_profit_rules()
        self.recalculate()

    def _mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
            self.dirtyChanged.emit(True)

    def mark_saved(self) -> None:
        self.dirty = False
        self.dirtyChanged.emit(False)

    def _build_image_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(6)
        header = SectionHeader("图片输入")
        minus = QPushButton("−")
        minus.setFixedWidth(32)
        plus = QPushButton("+")
        plus.setFixedWidth(32)
        self.slot_count_label = QLabel("5")
        self.slot_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slot_count_label.setFixedWidth(22)
        save_config = QPushButton("保存图片框配置")
        self.ai_button = QPushButton("AI识图")
        self.ai_button.setProperty("primary", True)
        minus.clicked.connect(lambda: self.change_slot_count(-1))
        plus.clicked.connect(lambda: self.change_slot_count(1))
        save_config.clicked.connect(self.save_image_config)
        self.ai_button.clicked.connect(self.run_recognition)
        for widget in (minus, self.slot_count_label, plus, save_config, self.ai_button):
            header.right_layout.addWidget(widget)
        layout.addWidget(header)
        self.image_slots_layout = QHBoxLayout()
        self.image_slots_layout.setSpacing(7)
        layout.addLayout(self.image_slots_layout)
        self.content_layout.addWidget(card)

    def _build_ai_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(5)
        first = QHBoxLayout()
        title = QLabel("AI识别摘要")
        title.setProperty("sectionTitle", True)
        first.addWidget(title)
        self.review_badge = QLabel("待识别")
        self.review_badge.setProperty("warning", True)
        first.addWidget(self.review_badge)
        self.product_summary = QuickLineEdit()
        self.product_summary.setPlaceholderText("商品类型/名称")
        self.material_summary = QuickLineEdit()
        self.material_summary.setPlaceholderText("主要材质")
        self.packaging_summary = QuickLineEdit()
        self.packaging_summary.setPlaceholderText("包装状态")
        self.packaging_summary.setReadOnly(True)
        reestimate = QPushButton("重新估算规格")
        reestimate.clicked.connect(self.reestimate_packaging)
        first.addWidget(self.product_summary, 3)
        first.addWidget(self.material_summary, 2)
        first.addWidget(self.packaging_summary, 2)
        first.addWidget(reestimate)
        layout.addLayout(first)

        second = QHBoxLayout()
        second.setSpacing(7)
        self.rigidity_combo = QComboBox()
        self.rigidity_combo.addItem("软硬：未知", "unknown")
        self.rigidity_combo.addItem("柔软", "soft")
        self.rigidity_combo.addItem("半硬", "semi_rigid")
        self.rigidity_combo.addItem("硬质", "hard")
        self.foldability_combo = QComboBox()
        self.foldability_combo.addItem("折叠：未知", "unknown")
        self.foldability_combo.addItem("不可折叠", "none")
        self.foldability_combo.addItem("有限折叠", "limited")
        self.foldability_combo.addItem("可折叠", "good")
        self.compressibility_combo = QComboBox()
        self.compressibility_combo.addItem("压缩：未知", "unknown")
        self.compressibility_combo.addItem("不可压缩", "none")
        self.compressibility_combo.addItem("有限压缩", "limited")
        self.compressibility_combo.addItem("可压缩", "good")
        second.addWidget(self.rigidity_combo)
        second.addWidget(self.foldability_combo)
        second.addWidget(self.compressibility_combo)
        self.structure_checks: dict[str, QCheckBox] = {}
        for key, text in (
            ("no_hard_structure", "无硬结构"),
            ("has_hard_bottom", "硬底"),
            ("has_hard_backboard", "硬背板"),
            ("has_frame", "框架"),
            ("has_rigid_insert", "硬内衬"),
            ("requires_shape_retention", "保形"),
            ("retail_box_visible", "原盒"),
            ("hard_card_visible", "硬卡"),
        ):
            box = QCheckBox(text)
            self.structure_checks[key] = box
            second.addWidget(box)
        second.addStretch(1)
        layout.addLayout(second)
        self.content_layout.addWidget(card)

    def _package_card(self, title: str, *, selected: bool = False) -> tuple[Card, dict[str, Any]]:
        card = Card(soft=True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(4)
        title_row = QHBoxLayout()
        radio = QRadioButton(title)
        radio.setChecked(selected)
        title_row.addWidget(radio)
        title_row.addStretch(1)
        changed = QLabel("")
        changed.setProperty("primary", True)
        title_row.addWidget(changed)
        layout.addLayout(title_row)
        method = QuickLineEdit()
        method.setPlaceholderText("包装方式")
        layout.addWidget(method)
        dims = QHBoxLayout()
        dims.setSpacing(3)
        length = LabeledSpin("长", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        width = LabeledSpin("宽", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        height = LabeledSpin("高", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        for widget in (length, width, height):
            dims.addWidget(widget)
        layout.addLayout(dims)
        weight = LabeledSpin("包装后重量", suffix="g", decimals=1, maximum=100000, input_width=84, special_text="—")
        layout.addWidget(weight)
        reason = QLabel("待估算")
        reason.setWordWrap(True)
        reason.setProperty("muted", True)
        reason.setMaximumHeight(34)
        layout.addWidget(reason)
        return card, {
            "name": title,
            "card": card,
            "radio": radio,
            "changed": changed,
            "method": method,
            "length": length,
            "width": width,
            "height": height,
            "weight": weight,
            "reason": reason,
        }

    def _build_cost_section(self) -> None:
        container = Card()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(6)
        header = SectionHeader("成本与规格")
        self.product_cost = LabeledSpin("商品成本", suffix="RMB", input_width=92, special_text="未填写")
        self.domestic_shipping = LabeledSpin("国内运费", suffix="RMB", input_width=82)
        self.tail_fee_usd = LabeledSpin("尾程费用", suffix="USD", input_width=74, value=float(self.settings.get("default_tail_fee_usd", 5.56)))
        self.tail_fee_rmb = LabeledSpin("", suffix="RMB", input_width=74, value=float(self.settings.get("default_tail_fee_rmb", 40.0)))
        for widget in (self.product_cost, self.domestic_shipping, self.tail_fee_usd, self.tail_fee_rmb):
            header.right_layout.addWidget(widget)
        layout.addWidget(header)

        self.decision_layout = QHBoxLayout()
        self.decision_layout.setSpacing(7)

        bare_card = Card()
        bare_layout = QVBoxLayout(bare_card)
        bare_layout.setContentsMargins(8, 7, 8, 8)
        bare_layout.setSpacing(4)
        bare_title = QLabel("裸尺寸")
        bare_title.setProperty("sectionTitle", True)
        bare_layout.addWidget(bare_title)
        bare_dims = QHBoxLayout()
        bare_dims.setSpacing(3)
        self.bare_length = LabeledSpin("长", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        self.bare_width = LabeledSpin("宽", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        self.bare_height = LabeledSpin("高", suffix="cm", decimals=1, maximum=500, input_width=62, special_text="—")
        for widget in (self.bare_length, self.bare_width, self.bare_height):
            bare_dims.addWidget(widget)
        bare_layout.addLayout(bare_dims)
        self.bare_weight = LabeledSpin("裸重", suffix="g", decimals=1, maximum=100000, input_width=84, special_text="—")
        bare_layout.addWidget(self.bare_weight)
        bare_layout.addStretch(1)

        normal_card, self.normal_fields = self._package_card("正常档", selected=True)
        conservative_card, self.conservative_fields = self._package_card("保守档")
        self.package_group = QButtonGroup(self)
        self.package_group.setExclusive(True)
        self.package_group.addButton(self.normal_fields["radio"], 0)
        self.package_group.addButton(self.conservative_fields["radio"], 1)
        self.normal_fields["radio"].clicked.connect(lambda: self._select_package("正常档", user=True))
        self.conservative_fields["radio"].clicked.connect(lambda: self._select_package("保守档", user=True))

        self.system_card = Card()
        system_layout = QVBoxLayout(self.system_card)
        system_layout.setContentsMargins(8, 7, 8, 8)
        system_layout.setSpacing(3)
        title = QLabel("当前总成本")
        title.setProperty("sectionTitle", True)
        system_layout.addWidget(title)
        self.system_rows: dict[str, QLabel] = {}
        for key, label in (
            ("package", "包装档"),
            ("forwarder", "货代"),
            ("actual", "实际重"),
            ("volume", "体积重"),
            ("chargeable", "计费重"),
            ("logistics", "物流总价"),
        ):
            row = QHBoxLayout()
            row.setSpacing(3)
            row.addWidget(QLabel(label))
            row.addStretch(1)
            value = QLabel("—")
            row.addWidget(value)
            self.system_rows[key] = value
            system_layout.addLayout(row)
        self.system_total = QLabel("—")
        self.system_total.setProperty("primary", True)
        self.system_total.setStyleSheet("font-size:22px;")
        system_layout.addWidget(self.system_total)

        self.decision_layout.addWidget(bare_card, 1)
        self.decision_layout.addWidget(normal_card, 1)
        self.decision_layout.addWidget(conservative_card, 1)
        self.quote_insert_index = 3
        self.decision_layout.addWidget(self.system_card, 1)
        layout.addLayout(self.decision_layout)
        self.content_layout.addWidget(container)
        self._select_package("正常档", user=False)
        self.rebuild_quote_cards()

    def _build_profit_section(self) -> None:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(5)
        header = SectionHeader("利润测算")
        self.shein_quote = LabeledSpin("SHEIN核价", suffix="USD", input_width=90)
        self.rule_combo = QComboBox()
        self.rule_combo.setMinimumWidth(230)
        self.rule_badge = QLabel("无利润规则")
        header.right_layout.addWidget(self.shein_quote)
        header.right_layout.addWidget(QLabel("利润规则"))
        header.right_layout.addWidget(self.rule_combo)
        header.right_layout.addWidget(self.rule_badge)
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.adopted_cost = LabeledSpin("计算采用总成本", suffix="RMB", maximum=1_000_000, input_width=100, special_text="—")
        self.adopted_cost.setReadOnly(True)
        self.sale_price = LabeledSpin("售价", suffix="USD", maximum=1_000_000, input_width=94)
        self.reserve_percent = LabeledSpin("活动/降价预留", suffix="%", maximum=99, value=0, input_width=72)
        self.profit_value = LabeledSpin("预测利润", suffix="RMB", minimum=-1_000_000, maximum=1_000_000, input_width=104, special_text="—")
        self.profit_value.setReadOnly(True)
        self.profit_rate = LabeledSpin("预计利润率", suffix="%", minimum=-10000, maximum=10000, input_width=92, special_text="—")
        self.profit_rate.setReadOnly(True)
        for widget in (self.adopted_cost, self.sale_price, self.reserve_percent, self.profit_value, self.profit_rate):
            row.addWidget(widget)
        row.addStretch(1)
        self.profit_state = QLabel("等待有效数据")
        self.profit_state.setProperty("warning", True)
        row.addWidget(self.profit_state)
        layout.addLayout(row)
        self.profit_explanation = QLabel("请补全成本、包装和货代数据。")
        self.profit_explanation.setWordWrap(True)
        self.profit_explanation.setProperty("muted", True)
        layout.addWidget(self.profit_explanation)
        self.content_layout.addWidget(card)

    def _build_bottom_actions(self) -> None:
        card = Card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 6, 10, 6)
        link_label = QLabel("商品链接")
        self.product_link = QuickLineEdit()
        self.product_link.setPlaceholderText("粘贴1688或其他商品链接，随记录保存")
        layout.addWidget(link_label)
        layout.addWidget(self.product_link, 1)
        layout.addSpacing(22)
        save = QPushButton("保存本次记录")
        save.setProperty("primary", True)
        save.setMinimumWidth(150)
        clear = QPushButton("清空并新建")
        clear.setMinimumWidth(140)
        save.clicked.connect(self.save_record)
        clear.clicked.connect(self.clear_new)
        layout.addWidget(save)
        layout.addSpacing(18)
        layout.addWidget(clear)
        self.content_layout.addWidget(card)

    def _connect_calculation_signals(self) -> None:
        for widget in (
            self.product_cost,
            self.domestic_shipping,
            self.tail_fee_usd,
            self.tail_fee_rmb,
            self.shein_quote,
            self.sale_price,
            self.reserve_percent,
        ):
            widget.valueChanged.connect(lambda _value: self._mark_dirty())
        self.product_link.textChanged.connect(lambda _text: self._mark_dirty())

        for name, fields in (("正常档", self.normal_fields), ("保守档", self.conservative_fields)):
            fields["method"].textEdited.connect(lambda _text, n=name: self._scenario_manually_changed(n))
            for key in ("length", "width", "height", "weight"):
                fields[key].valueChanged.connect(lambda _value, n=name: self._scenario_manually_changed(n))

        self.product_cost.editingFinished.connect(self.recalculate)
        self.domestic_shipping.editingFinished.connect(self.recalculate)
        for widget in (self.bare_length, self.bare_width, self.bare_height, self.bare_weight):
            widget.editingFinished.connect(self._upstream_changed)
        self.product_summary.textChanged.connect(lambda _text: self._upstream_changed())
        self.material_summary.textChanged.connect(lambda _text: self._upstream_changed())
        for combo in (self.rigidity_combo, self.foldability_combo, self.compressibility_combo):
            combo.currentIndexChanged.connect(lambda _index: self._upstream_changed())
        for key, box in self.structure_checks.items():
            if key == "no_hard_structure":
                box.toggled.connect(self._on_no_structure_toggled)
            else:
                box.toggled.connect(lambda checked, k=key: self._on_structure_toggled(k, checked))
        self.tail_fee_rmb.editingFinished.connect(self._tail_rmb_changed)
        self.tail_fee_usd.editingFinished.connect(self._tail_usd_changed)
        self.sale_price.editingFinished.connect(self._forward_profit)
        self.reserve_percent.editingFinished.connect(self._forward_profit)
        self.rule_combo.currentIndexChanged.connect(self._profit_rule_changed)

    def _on_no_structure_toggled(self, checked: bool) -> None:
        if self._updating:
            return
        if checked:
            self._updating = True
            for key, box in self.structure_checks.items():
                if key != "no_hard_structure":
                    box.setChecked(False)
            self._updating = False
        self._upstream_changed()

    def _on_structure_toggled(self, _key: str, checked: bool) -> None:
        if self._updating:
            return
        if checked and self.structure_checks["no_hard_structure"].isChecked():
            self._updating = True
            self.structure_checks["no_hard_structure"].setChecked(False)
            self._updating = False
        self._upstream_changed()

    def rebuild_image_slots(self, count: int) -> None:
        while self.image_slots_layout.count():
            item = self.image_slots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        existing = [(slot.path, slot.image_type()) for slot in self.image_slots]
        self.image_slots = []
        types = list(self.settings.get("image_slot_types", []))
        defaults = [ImageType.MAIN, ImageType.PRODUCT_INFO, ImageType.DIMENSION_WEIGHT]
        for index in range(count):
            try:
                image_type = ImageType(types[index])
            except (IndexError, ValueError):
                image_type = defaults[index % len(defaults)]
            slot = ImageSlotWidget(index, image_type)
            slot.changed.connect(self._mark_dirty)
            slot.removeRequested.connect(self.remove_image)
            if index < len(existing) and existing[index][0] is not None:
                slot.load_path(existing[index][0])
                slot.set_image_type(existing[index][1])
            self.image_slots.append(slot)
            self.image_slots_layout.addWidget(slot)
        self.slot_count_label.setText(str(count))

    def change_slot_count(self, delta: int) -> None:
        new_count = len(self.image_slots) + delta
        if not 3 <= new_count <= 6:
            return
        if delta < 0 and self.image_slots[-1].path is not None:
            QMessageBox.information(self, "无法减少", "请先删除最后一个图片框中的图片。")
            return
        self.rebuild_image_slots(new_count)
        self._mark_dirty()

    def save_image_config(self) -> None:
        self.settings["image_slot_count"] = len(self.image_slots)
        self.settings["image_slot_types"] = [slot.image_type().value for slot in self.image_slots]
        self.context.settings_service.save(self.settings)
        QMessageBox.information(self, "已保存", "图片框数量、顺序和默认类型已保存。")

    def remove_image(self, index: int) -> None:
        if 0 <= index < len(self.image_slots):
            self.image_slots[index].clear_image()

    def paste_from_clipboard(self) -> bool:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    target = next((slot for slot in self.image_slots if slot.path is None), self.image_slots[0])
                    target.load_path(Path(url.toLocalFile()))
                    return True
        image = clipboard.image()
        if not image.isNull():
            array = QByteArray()
            buffer = QBuffer(array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            data = bytes(array)
            digest = hashlib.sha256(data).hexdigest()
            temp_dir = Path(tempfile.gettempdir()) / "profit_accounting_26_clipboard"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp = temp_dir / f"clipboard_{digest[:20]}.png"
            if not temp.exists():
                temp.write_bytes(data)
            target = next((slot for slot in self.image_slots if slot.path is None), self.image_slots[0])
            target.load_path(temp)
            return True
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Paste) and self.paste_from_clipboard():
            event.accept()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _apply_observation(self, observation: AIObservation) -> None:
        previous_updating = self._updating
        self._updating = True
        if observation.product_name or observation.product_type:
            self.product_summary.setText(observation.product_name or observation.product_type)
        if observation.material:
            self.material_summary.setText(observation.material)
        self._set_combo_data(self.rigidity_combo, observation.rigidity)
        self._set_combo_data(self.foldability_combo, observation.foldability)
        self._set_combo_data(self.compressibility_combo, observation.compressibility)
        if observation.product_cost_rmb is not None:
            self.product_cost.setValue(observation.product_cost_rmb)
        if observation.domestic_shipping_rmb is not None:
            self.domestic_shipping.setValue(observation.domestic_shipping_rmb)
        if observation.length_cm is not None:
            self.bare_length.setValue(observation.length_cm)
        if observation.width_cm is not None:
            self.bare_width.setValue(observation.width_cm)
        if observation.height_cm is not None:
            self.bare_height.setValue(observation.height_cm)
        if observation.weight_g is not None:
            self.bare_weight.setValue(observation.weight_g)
        flags = {
            "has_hard_bottom": observation.has_hard_bottom,
            "has_hard_backboard": observation.has_hard_backboard,
            "has_frame": observation.has_frame,
            "has_rigid_insert": observation.has_rigid_insert,
            "requires_shape_retention": observation.requires_shape_retention,
            "retail_box_visible": observation.retail_box_visible,
            "hard_card_visible": observation.hard_card_visible,
        }
        for key, value in flags.items():
            self.structure_checks[key].setChecked(value is True)
        known_false = flags and all(value is False for value in flags.values())
        self.structure_checks["no_hard_structure"].setChecked(known_false)
        self._updating = previous_updating

    def run_recognition(self) -> None:
        if self._recognition_thread is not None:
            return
        image_items = [
            {"path": str(slot.path), "type": slot.image_type().value}
            for slot in self.image_slots
            if slot.path
        ]
        if not image_items:
            QMessageBox.information(self, "没有图片", "请先导入至少一张图片。")
            return
        self._show_recognition_dialog()
        self.ai_button.setEnabled(False)
        self._recognition_cancellation = RecognitionCancellation()
        self._recognition_thread = QThread(self)
        self._recognition_worker = RecognitionWorker(
            self.context.recognition_service,
            image_items,
            self._recognition_cancellation,
        )
        self._recognition_worker.moveToThread(self._recognition_thread)
        self._recognition_thread.started.connect(self._recognition_worker.run)
        self._recognition_worker.completed.connect(self._recognition_completed)
        self._recognition_worker.failed.connect(self._recognition_failed)
        self._recognition_worker.completed.connect(self._recognition_thread.quit)
        self._recognition_worker.failed.connect(self._recognition_thread.quit)
        self._recognition_thread.finished.connect(self._recognition_thread_finished)
        self._recognition_thread.finished.connect(self._recognition_worker.deleteLater)
        self._recognition_thread.start()

    def _show_recognition_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("AI识图")
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setFixedSize(300, 118)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        label = QLabel("AI识图中，请稍候")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("sectionTitle", True)
        stop = QPushButton("终止")
        stop.setFixedSize(86, 30)
        stop.setProperty("danger", True)
        stop.clicked.connect(self.cancel_recognition)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addStretch(1)
        actions.addWidget(stop)
        actions.addStretch(1)
        layout.addWidget(label)
        layout.addLayout(actions)
        self._recognition_dialog = dialog
        dialog.show()

    def cancel_recognition(self) -> None:
        if self._recognition_cancellation is None or self._recognition_dialog is None:
            return
        self._recognition_cancellation.cancel()
        for button in self._recognition_dialog.findChildren(QPushButton):
            button.setEnabled(False)
        for label in self._recognition_dialog.findChildren(QLabel):
            label.setText("正在终止 AI识图…")

    @Slot(object, object)
    def _recognition_completed(self, observation: AIObservation, external_proposal: PackagingProposal | None) -> None:
        self.observation = observation
        self._apply_observation(observation)
        self.proposal = self.context.packaging_service.estimate(observation, external_proposal=external_proposal)
        self.apply_proposal(self.proposal)
        self.packaging_stale = False
        self.manual_scenarios.clear()
        self._mark_dirty()
        self.recalculate()

    @Slot(str, str)
    def _recognition_failed(self, category: str, message: str) -> None:
        if category == "cancelled":
            return
        title = {
            "unavailable": "AI识图不可用",
            "response": "AI返回无效",
        }.get(category, "AI识图失败")
        QMessageBox.warning(self, title, message)

    def _recognition_thread_finished(self) -> None:
        if self._recognition_dialog is not None:
            self._recognition_dialog.close()
            self._recognition_dialog.deleteLater()
        thread = self._recognition_thread
        self._recognition_dialog = None
        self._recognition_worker = None
        self._recognition_cancellation = None
        self._recognition_thread = None
        self.ai_button.setEnabled(True)
        if thread is not None:
            thread.deleteLater()

    def collect_observation(self) -> AIObservation:
        observation = AIObservation.from_dict(self.observation.to_dict())
        observation.product_name = self.product_summary.text().strip()
        observation.product_type = self.product_summary.text().strip()
        observation.material = self.material_summary.text().strip()
        observation.rigidity = str(self.rigidity_combo.currentData())
        observation.foldability = str(self.foldability_combo.currentData())
        observation.compressibility = str(self.compressibility_combo.currentData())
        no_structure = self.structure_checks["no_hard_structure"].isChecked()
        for key in (
            "has_hard_bottom",
            "has_hard_backboard",
            "has_frame",
            "has_rigid_insert",
            "requires_shape_retention",
            "retail_box_visible",
            "hard_card_visible",
        ):
            checked = self.structure_checks[key].isChecked()
            setattr(observation, key, checked if checked else (False if no_structure else None))
        rigid_values = [
            getattr(observation, key)
            for key in ("has_hard_bottom", "has_hard_backboard", "has_frame", "has_rigid_insert")
        ]
        observation.has_rigid_parts = (
            True if any(value is True for value in rigid_values)
            else (False if no_structure else None)
        )
        observation.length_cm = self.bare_length.value() or None
        observation.width_cm = self.bare_width.value() or None
        observation.height_cm = self.bare_height.value() or None
        observation.weight_g = self.bare_weight.value() or None
        observation.product_cost_rmb = self.product_cost.value() or None
        observation.domestic_shipping_rmb = self.domestic_shipping.value()
        return observation

    def reestimate_packaging(self) -> None:
        self.observation = self.collect_observation()
        self.proposal = self.context.packaging_service.estimate(self.observation)
        self.apply_proposal(self.proposal)
        self.packaging_stale = False
        self.manual_scenarios.clear()
        self._mark_dirty()
        self.recalculate()

    def apply_proposal(self, proposal: PackagingProposal) -> None:
        previous_updating = self._updating
        self._updating = True
        for scenario, fields in ((proposal.normal, self.normal_fields), (proposal.conservative, self.conservative_fields)):
            fields["method"].setText(scenario.packaging_method)
            fields["length"].setValue(scenario.length_cm or 0)
            fields["width"].setValue(scenario.width_cm or 0)
            fields["height"].setValue(scenario.height_cm or 0)
            fields["weight"].setValue(scenario.weight_g or 0)
            fields["reason"].setText(scenario.reasoning_summary or "待人工补充")
            fields["changed"].setText("")
        self._updating = previous_updating
        summary = proposal.normal.packaging_method or "包装信息待补充"
        self.packaging_summary.setText(summary)
        if proposal.needs_review:
            self.review_badge.setText("需要复核")
            self.review_badge.setProperty("warning", True)
            self.review_badge.setProperty("success", False)
        else:
            self.review_badge.setText("已识别")
            self.review_badge.setProperty("success", True)
            self.review_badge.setProperty("warning", False)
        self._refresh_badge_style()

    def _refresh_badge_style(self) -> None:
        self.review_badge.style().unpolish(self.review_badge)
        self.review_badge.style().polish(self.review_badge)

    def _upstream_changed(self) -> None:
        if self._updating:
            return
        self._mark_dirty()
        if self.proposal is not None:
            self.packaging_stale = True
            self.packaging_summary.setText("包装估算已过期")
            self.review_badge.setText("估算已过期 · 禁止保存")
            self.review_badge.setProperty("warning", True)
            self.review_badge.setProperty("success", False)
            self._refresh_badge_style()
        self.recalculate()

    def _scenario_manually_changed(self, name: str) -> None:
        if self._updating:
            return
        self.manual_scenarios.add(name)
        fields = self.normal_fields if name == "正常档" else self.conservative_fields
        fields["reason"].setText("人工修改 · 需要复核")
        fields["changed"].setText("✓")
        self.review_badge.setText("人工修改 · 需要复核")
        self.review_badge.setProperty("warning", True)
        self.review_badge.setProperty("success", False)
        self._refresh_badge_style()
        self._mark_dirty()
        self.recalculate()

    def _select_package(self, name: str, *, user: bool) -> None:
        normal_selected = name == "正常档"
        self.normal_fields["radio"].setChecked(normal_selected)
        self.conservative_fields["radio"].setChecked(not normal_selected)
        if user:
            self.package_selection_changed = True
            self._mark_dirty()
        for fields, selected in ((self.normal_fields, normal_selected), (self.conservative_fields, not normal_selected)):
            fields["card"].set_choice_state(selected=selected, frozen=not selected)
            fields["method"].setEnabled(selected)
            for key in ("length", "width", "height", "weight"):
                fields[key].setEnabled(selected)
            fields["changed"].setText("✓" if selected and self.package_selection_changed else "")
        if hasattr(self, "profit_explanation"):
            self.recalculate()

    def current_scenario(self) -> PackagingScenario:
        fields = self.normal_fields if self.normal_fields["radio"].isChecked() else self.conservative_fields
        label = str(fields["name"])
        source = None
        if self.proposal:
            source = self.proposal.normal if label == "正常档" else self.proposal.conservative
        manual = label in self.manual_scenarios
        return PackagingScenario(
            label=label,
            packaging_state=source.packaging_state if source else self.observation_to_state(),
            packaging_method=fields["method"].text().strip(),
            length_cm=fields["length"].value() or None,
            width_cm=fields["width"].value() or None,
            height_cm=fields["height"].value() or None,
            weight_g=fields["weight"].value() or None,
            reasoning_summary=fields["reason"].text(),
            confidence="low" if manual else (source.confidence if source else "low"),
            needs_review=True if manual else (source.needs_review if source else True),
            default_fields_used=list(source.default_fields_used) if source else [],
        )

    def observation_to_state(self):
        from profit_accounting_26.domain.models import PackagingState
        return PackagingState.UNKNOWN

    def rebuild_quote_cards(self) -> None:
        for card in self.quote_cards.values():
            self.decision_layout.removeWidget(card)
            card.deleteLater()
        self.quote_cards = {}
        forwarders = self.context.settings_service.forwarders_from_settings(self.settings)
        enabled = [item for item in forwarders if item.enabled and not item.archived]
        priority = {"义乌货代": 0, "深圳货代": 1}
        enabled.sort(key=lambda item: (priority.get(item.name, 9), item.name))
        if enabled and self.selected_forwarder_id not in {item.id for item in enabled}:
            self.selected_forwarder_id = enabled[0].id
        for offset, forwarder in enumerate(enabled):
            card = QuoteCard(forwarder.id, forwarder.name)
            card.selected.connect(self.select_forwarder)
            card.set_checked(
                forwarder.id == self.selected_forwarder_id,
                user_changed=self.forwarder_selection_changed,
            )
            self.quote_cards[forwarder.id] = card
            self.decision_layout.insertWidget(self.quote_insert_index + offset, card, 1)

    def select_forwarder(self, forwarder_id: str) -> None:
        self.selected_forwarder_id = forwarder_id
        self.forwarder_selection_changed = True
        for identifier, card in self.quote_cards.items():
            card.set_checked(identifier == forwarder_id, user_changed=True)
        self._mark_dirty()
        self.recalculate()

    def _tail_usd_changed(self) -> None:
        rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        self._updating = True
        self.tail_fee_rmb.setValue(self.tail_fee_usd.value() * rate)
        self._updating = False
        self.settings["default_tail_fee_usd"] = self.tail_fee_usd.value()
        self.settings["default_tail_fee_rmb"] = self.tail_fee_rmb.value()
        self.context.settings_service.save(self.settings)
        self.recalculate()

    def _tail_rmb_changed(self) -> None:
        if self._updating:
            return
        rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        self._updating = True
        self.tail_fee_usd.setValue(self.tail_fee_rmb.value() / rate if rate else 0)
        self._updating = False
        self.settings["default_tail_fee_usd"] = self.tail_fee_usd.value()
        self.settings["default_tail_fee_rmb"] = self.tail_fee_rmb.value()
        self.context.settings_service.save(self.settings)
        self.recalculate()

    def _clear_calculation(self, message: str) -> None:
        self.current_quote = None
        self.current_forwarder = None
        self.current_system_cost = None
        for card in self.quote_cards.values():
            card.update_quote(None)
        for value in self.system_rows.values():
            value.setText("—")
        self.system_total.setText("—")
        self._updating = True
        self.adopted_cost.setValue(0)
        self.profit_value.setValue(0)
        self.profit_rate.setValue(0)
        self._updating = False
        self.profit_value.spin.setStyleSheet("")
        self.profit_rate.spin.setStyleSheet("")
        self.profit_state.setText("等待有效数据")
        self.profit_state.setProperty("warning", True)
        self.profit_state.setProperty("success", False)
        self.profit_state.setProperty("danger", False)
        self._refresh_profit_style()
        self.profit_explanation.setText(message)

    def recalculate(self) -> None:
        if self._updating:
            return
        if self.packaging_stale:
            self._clear_calculation("包装估算已过期，请重新估算后再计算和保存。")
            return
        scenario = self.current_scenario()
        forwarders = self.context.settings_service.forwarders_from_settings(self.settings)
        enabled = [item for item in forwarders if item.enabled and not item.archived]
        if self.product_cost.value() <= 0:
            self._clear_calculation("请填写有效商品成本。")
            return
        if not scenario.is_complete() or not enabled:
            self._clear_calculation("请补全当前包装档的尺寸、重量，并确保至少启用一家货代。")
            return
        package = scenario.to_package_spec()
        quotes = self.calculation_service.quote_all_forwarders(
            package=package,
            forwarders=enabled,
            tail_fee_rmb=self.tail_fee_rmb.value(),
        )
        cheapest_id = min(quotes, key=lambda key: quotes[key].total_logistics_rmb) if quotes else ""
        for identifier, card in self.quote_cards.items():
            card.update_quote(quotes.get(identifier), cheapest=identifier == cheapest_id)
        selected_quote = quotes.get(self.selected_forwarder_id)
        selected_forwarder = next((item for item in enabled if item.id == self.selected_forwarder_id), None)
        if selected_quote is None and enabled:
            self.selected_forwarder_id = enabled[0].id
            self.recalculate()
            return
        if selected_quote is None or selected_forwarder is None:
            self._clear_calculation("当前货代不可用。")
            return
        self.current_quote = selected_quote
        self.current_forwarder = selected_forwarder
        system_cost = self.product_cost.value() + self.domestic_shipping.value() + selected_quote.total_logistics_rmb
        self.current_system_cost = system_cost
        self._updating = True
        self.adopted_cost.setValue(system_cost)
        self._updating = False
        self.system_rows["package"].setText(scenario.label)
        self.system_rows["forwarder"].setText(selected_forwarder.name)
        self.system_rows["actual"].setText(f"{selected_quote.actual_weight_kg:.3f} kg")
        self.system_rows["volume"].setText(f"{selected_quote.volume_weight_kg:.3f} kg")
        self.system_rows["chargeable"].setText(f"{selected_quote.chargeable_weight_kg:.3f} kg")
        self.system_rows["logistics"].setText(f"¥{selected_quote.total_logistics_rmb:.2f}")
        self.system_total.setText(f"¥{system_cost:.2f}")
        self._forward_profit()

    def rebuild_profit_rules(self) -> None:
        self.rule_combo.blockSignals(True)
        self.rule_combo.clear()
        rules = [rule for rule in self.context.settings_service.rules_from_settings(self.settings) if rule.enabled and not rule.archived]
        if not rules:
            self.rule_combo.addItem("无利润规则", "")
            self.selected_profit_rule_id = ""
        else:
            for rule in rules:
                self.rule_combo.addItem(rule.name, rule.id)
            ids = [rule.id for rule in rules]
            if self.selected_profit_rule_id not in ids:
                self.selected_profit_rule_id = ids[0]
            index = self.rule_combo.findData(self.selected_profit_rule_id)
            self.rule_combo.setCurrentIndex(max(0, index))
        self.rule_combo.blockSignals(False)

    def _profit_rule_changed(self, _index: int) -> None:
        if self._updating:
            return
        self.selected_profit_rule_id = str(self.rule_combo.currentData() or "")
        self.settings["selected_profit_rule_id"] = self.selected_profit_rule_id
        self.context.settings_service.save(self.settings)
        self._mark_dirty()
        self._forward_profit()

    def _active_rules(self):
        return [
            rule
            for rule in self.context.settings_service.rules_from_settings(self.settings)
            if rule.enabled and not rule.archived and rule.id == self.selected_profit_rule_id
        ]

    def _refresh_profit_style(self) -> None:
        self.profit_state.style().unpolish(self.profit_state)
        self.profit_state.style().polish(self.profit_state)

    def _forward_profit(self) -> None:
        if self._updating:
            return
        if self.current_system_cost is None or self.packaging_stale:
            self._clear_calculation("等待有效成本、包装和货代数据。")
            return
        rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        if self.sale_price.value() <= 0 or rate <= 0:
            self._updating = True
            self.profit_value.setValue(0)
            self.profit_rate.setValue(0)
            self._updating = False
            self.profit_state.setText("等待售价")
            self.profit_state.setProperty("warning", True)
            self.profit_state.setProperty("success", False)
            self.profit_state.setProperty("danger", False)
            self._refresh_profit_style()
            self.profit_explanation.setText("填写售价后计算预测利润。")
            return
        try:
            from profit_accounting_26.engines.profit import calculate_profit
            result = calculate_profit(
                total_cost_rmb=self.adopted_cost.value(),
                sale_price_usd=self.sale_price.value(),
                exchange_rate=rate,
                reserve_rate=self.reserve_percent.value() / 100.0,
                rules=self._active_rules(),
            )
        except ValueError as exc:
            self.profit_explanation.setText(str(exc))
            return
        self._updating = True
        self.profit_value.setValue(result.profit_rmb)
        self.profit_rate.setValue((result.profit_rate_on_cost or 0.0) * 100.0)
        self._updating = False
        applied = []
        context = {
            "sale_price_usd": result.sale_price_usd,
            "sale_price_rmb": result.sale_price_rmb,
            "revenue_after_reserve_rmb": result.revenue_after_reserve_rmb,
            "total_cost_rmb": result.total_cost_rmb,
        }
        for rule in self._active_rules():
            income, cost = evaluate_rule(rule, context, exchange_rate=rate)
            if income or cost:
                applied.append(f"{rule.name} {'+' if income else '-'}¥{income or cost:.2f}")
        self.rule_badge.setText("；".join(applied) if applied else "未触发调整")
        if result.profit_rmb >= 0:
            self.profit_state.setText("盈利")
            self.profit_state.setProperty("success", True)
            self.profit_state.setProperty("danger", False)
            self.profit_state.setProperty("warning", False)
            self.profit_value.spin.setStyleSheet("color:#219B68;font-weight:600;")
            self.profit_rate.spin.setStyleSheet("color:#219B68;font-weight:600;")
        else:
            self.profit_state.setText("亏损")
            self.profit_state.setProperty("danger", True)
            self.profit_state.setProperty("success", False)
            self.profit_state.setProperty("warning", False)
            self.profit_value.spin.setStyleSheet("color:#D94A4A;font-weight:600;")
            self.profit_rate.spin.setStyleSheet("color:#D94A4A;font-weight:600;")
        self._refresh_profit_style()
        reduced_price = result.sale_price_usd * (1 - self.reserve_percent.value() / 100.0)
        self.profit_explanation.setText(
            f"售价 ${result.sale_price_usd:.2f}，预留后 ${reduced_price:.2f}；"
            f"采用成本 ¥{result.total_cost_rmb:.2f}，预测利润 ¥{result.profit_rmb:.2f}。"
        )

    def build_record_payload(self) -> dict[str, Any]:
        scenario = self.current_scenario()
        normal = PackagingScenario(
            label="正常档",
            packaging_state=self.proposal.normal.packaging_state if self.proposal else scenario.packaging_state,
            packaging_method=self.normal_fields["method"].text(),
            length_cm=self.normal_fields["length"].value() or None,
            width_cm=self.normal_fields["width"].value() or None,
            height_cm=self.normal_fields["height"].value() or None,
            weight_g=self.normal_fields["weight"].value() or None,
            reasoning_summary=self.normal_fields["reason"].text(),
            confidence="low" if "正常档" in self.manual_scenarios else "medium",
            needs_review="正常档" in self.manual_scenarios,
        )
        conservative = PackagingScenario(
            label="保守档",
            packaging_state=self.proposal.conservative.packaging_state if self.proposal else scenario.packaging_state,
            packaging_method=self.conservative_fields["method"].text(),
            length_cm=self.conservative_fields["length"].value() or None,
            width_cm=self.conservative_fields["width"].value() or None,
            height_cm=self.conservative_fields["height"].value() or None,
            weight_g=self.conservative_fields["weight"].value() or None,
            reasoning_summary=self.conservative_fields["reason"].text(),
            confidence="low" if "保守档" in self.manual_scenarios else "medium",
            needs_review="保守档" in self.manual_scenarios,
        )
        return {
            "product_name": self.product_summary.text().strip(),
            "product_link": self.product_link.text().strip(),
            "status": "active",
            "layers": {
                "ai_raw": {
                    "observation": self.collect_observation().to_dict(),
                    "packaging_proposal": self.proposal.to_dict() if self.proposal else {},
                },
                "adopted": {
                    "bare": {
                        "length_cm": self.bare_length.value() or None,
                        "width_cm": self.bare_width.value() or None,
                        "height_cm": self.bare_height.value() or None,
                        "weight_g": self.bare_weight.value() or None,
                    },
                    "normal": normal.to_dict(),
                    "conservative": conservative.to_dict(),
                    "selected_packaging": scenario.label,
                    "selected_forwarder_id": self.selected_forwarder_id,
                    "calculation_cost_rmb": self.adopted_cost.value(),
                    "packaging_estimate_stale": self.packaging_stale,
                },
                "calculated": {
                    "system_cost_rmb": self.current_system_cost,
                    "sale_price_usd": self.sale_price.value(),
                    "reserve_percent": self.reserve_percent.value(),
                    "profit_rmb": self.profit_value.value(),
                    "profit_rate_percent": self.profit_rate.value(),
                    "exchange_rate": float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)),
                    "tail_fee_rmb": self.tail_fee_rmb.value(),
                    "selected_profit_rule_id": self.selected_profit_rule_id,
                    "total_logistics_rmb": self.current_quote.total_logistics_rmb if self.current_quote else None,
                    "logistics_quote": asdict(self.current_quote) if self.current_quote else {},
                    "forwarder_name": self.current_forwarder.name if self.current_forwarder else "",
                    "logistics_engine_version": "deterministic-logistics-v1",
                    "packaging_engine_version": self.context.packaging_service.ENGINE_VERSION,
                    "calibration_version": self.context.packaging_service.calibration_version,
                    "schema_version": "2.6.1",
                },
                "actual": {},
            },
            "product_cost_rmb": self.product_cost.value(),
            "domestic_shipping_rmb": self.domestic_shipping.value(),
            "shein_quote_usd": self.shein_quote.value(),
        }

    def save_record(self) -> None:
        if self.packaging_stale:
            QMessageBox.warning(self, "无法保存", "包装估算已过期，请先重新估算规格。")
            return
        if self.current_quote is None or self.current_system_cost is None:
            QMessageBox.warning(self, "无法保存", "请先补全成本、包装和货代数据。")
            return
        images = ImageSession(len(self.image_slots))
        for slot in self.image_slots:
            if slot.path:
                images.add_path(slot.path, slot.image_type())
        try:
            self.record_id = self.context.record_service.save(
                self.build_record_payload(), images=images.images, record_id=self.record_id
            )
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.mark_saved()
        self.saved.emit(self.record_id)
        QMessageBox.information(self, "保存成功", f"记录已保存：{self.record_id}")

    def clear_new(self) -> None:
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "清空并新建",
                "当前存在未保存修改，确定清空并新建吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._updating = True
        self.record_id = None
        self.observation = AIObservation()
        self.proposal = None
        self.packaging_stale = False
        self.manual_scenarios.clear()
        self.product_summary.clear()
        self.material_summary.clear()
        self.packaging_summary.clear()
        self.product_link.clear()
        for combo in (self.rigidity_combo, self.foldability_combo, self.compressibility_combo):
            combo.setCurrentIndex(0)
        for box in self.structure_checks.values():
            box.setChecked(False)
        for widget in (
            self.product_cost,
            self.domestic_shipping,
            self.bare_length,
            self.bare_width,
            self.bare_height,
            self.bare_weight,
            self.adopted_cost,
            self.shein_quote,
            self.sale_price,
            self.reserve_percent,
            self.profit_value,
            self.profit_rate,
        ):
            widget.setValue(0)
        for fields in (self.normal_fields, self.conservative_fields):
            fields["method"].clear()
            for key in ("length", "width", "height", "weight"):
                fields[key].setValue(0)
            fields["reason"].setText("待估算")
            fields["changed"].setText("")
        for slot in self.image_slots:
            slot.clear_image()
        self._updating = False
        self.package_selection_changed = False
        self.forwarder_selection_changed = False
        self._select_package("正常档", user=False)
        self.review_badge.setText("待识别")
        self.review_badge.setProperty("warning", True)
        self.mark_saved()
        self.recalculate()

    def load_record_payload(self, record_id: str) -> None:
        try:
            record = self.context.record_service.load(record_id)
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        self._updating = True
        self.manual_scenarios.clear()
        self.record_id = record_id
        self.product_summary.setText(str(record.get("product_name") or ""))
        self.product_link.setText(str(record.get("product_link") or ""))
        self.product_cost.setValue(float(record.get("product_cost_rmb", 0)))
        self.domestic_shipping.setValue(float(record.get("domestic_shipping_rmb", 0)))
        self.shein_quote.setValue(float(record.get("shein_quote_usd", 0)))
        layers = record.get("layers", {})
        ai_raw = layers.get("ai_raw", {})
        observation_raw = ai_raw.get("observation") or {}
        if observation_raw:
            self.observation = AIObservation.from_dict(observation_raw)
            self._apply_observation(self.observation)
        proposal_raw = ai_raw.get("packaging_proposal") or {}
        if proposal_raw:
            try:
                self.proposal = PackagingProposal.from_dict(proposal_raw)
            except Exception:
                self.proposal = None
        adopted = layers.get("adopted", {})
        self.packaging_stale = bool(adopted.get("packaging_estimate_stale", False))
        bare = adopted.get("bare", {})
        self.bare_length.setValue(float(bare.get("length_cm") or 0))
        self.bare_width.setValue(float(bare.get("width_cm") or 0))
        self.bare_height.setValue(float(bare.get("height_cm") or 0))
        self.bare_weight.setValue(float(bare.get("weight_g") or 0))
        for key, fields in (("normal", self.normal_fields), ("conservative", self.conservative_fields)):
            raw = adopted.get(key, {})
            fields["method"].setText(str(raw.get("packaging_method") or ""))
            fields["length"].setValue(float(raw.get("length_cm") or 0))
            fields["width"].setValue(float(raw.get("width_cm") or 0))
            fields["height"].setValue(float(raw.get("height_cm") or 0))
            fields["weight"].setValue(float(raw.get("weight_g") or 0))
            fields["reason"].setText(str(raw.get("reasoning_summary") or ""))
            if raw.get("needs_review"):
                self.manual_scenarios.add("正常档" if key == "normal" else "保守档")
        selected_package = str(adopted.get("selected_packaging") or "正常档")
        self.selected_forwarder_id = str(adopted.get("selected_forwarder_id") or self.selected_forwarder_id)
        calculated = layers.get("calculated", {})
        self.sale_price.setValue(float(calculated.get("sale_price_usd") or 0))
        self.reserve_percent.setValue(float(calculated.get("reserve_percent") or 0))
        self.selected_profit_rule_id = str(calculated.get("selected_profit_rule_id") or self.selected_profit_rule_id)
        for slot in self.image_slots:
            slot.clear_image()
        for index, image in enumerate(record.get("images", [])):
            if index >= len(self.image_slots):
                break
            path = self.context.paths.data_dir / str(image.get("relative_path") or "")
            if path.is_file():
                self.image_slots[index].load_path(path)
                try:
                    self.image_slots[index].set_image_type(ImageType(str(image.get("image_type"))))
                except ValueError:
                    pass
        self._updating = False
        self.rebuild_quote_cards()
        self.rebuild_profit_rules()
        self._select_package(selected_package, user=False)
        if self.packaging_stale:
            self.packaging_summary.setText("包装估算已过期")
            self.review_badge.setText("估算已过期 · 禁止保存")
            self.review_badge.setProperty("warning", True)
            self.review_badge.setProperty("success", False)
        elif self.proposal is not None:
            self.packaging_summary.setText(self.proposal.normal.packaging_method or "包装方案已载入")
            if self.proposal.needs_review or self.manual_scenarios:
                self.review_badge.setText("需要复核")
                self.review_badge.setProperty("warning", True)
                self.review_badge.setProperty("success", False)
            else:
                self.review_badge.setText("已载入")
                self.review_badge.setProperty("success", True)
                self.review_badge.setProperty("warning", False)
        else:
            self.packaging_summary.setText("人工包装方案")
            self.review_badge.setText("人工方案 · 需要复核")
            self.review_badge.setProperty("warning", True)
            self.review_badge.setProperty("success", False)
        self._refresh_badge_style()
        self.recalculate()
        self.mark_saved()

    def set_product_link(self, link: str) -> None:
        if link.strip():
            self.product_link.setText(link.strip())

    def refresh_settings(self) -> None:
        self.settings = self.context.settings_service.load()
        self.selected_forwarder_id = str(self.settings.get("selected_forwarder_id") or self.selected_forwarder_id)
        self.selected_profit_rule_id = str(self.settings.get("selected_profit_rule_id") or self.selected_profit_rule_id)
        self._updating = True
        self.tail_fee_usd.setValue(float(self.settings.get("default_tail_fee_usd", 5.56)))
        self.tail_fee_rmb.setValue(float(self.settings.get("default_tail_fee_rmb", 40.0)))
        self._updating = False
        self.rebuild_quote_cards()
        self.rebuild_profit_rules()
        self.recalculate()
