"""新商品测算页 —— 冻结 UI 绑定版（2.6.1-dual-profit）。

架构：
- 布局完全来自 ``forms/main_window.ui`` 的 ``pageCalculation``（QUiLoader 运行时加载，
  不生成 Python 布局副本）；
- 控件按 ``objectName`` 用 ``findChild`` 获取；
- 图片框（3–6 个）与货代报价卡片为运行时动态生成，分别挂到
  ``imageSlotsLayout`` / ``forwarderCardsLayout``（Designer 预览卡片被清除）；
- 利润双场景（无活动 / 活动后）委托 ``CalculationBinder`` 的 driver 状态机；
- AI 识图与按修正重估走 V1 轻量合同；物流、利润和记录保存沿用稳定链路。
"""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any

from PySide6.QtCore import QEvent, QObject, QThread, Qt, QSignalBlocker, Signal, Slot
from PySide6.QtGui import QDoubleValidator, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from profit_accounting_26.application import AppContext, CalculationService, ImageSession
from profit_accounting_26.application.api_profile_store import LOCAL_REESTIMATE, VISUAL_AI
from profit_accounting_26.application.calculation_session import CalculationSession
from profit_accounting_26.application.category_normalizer import normalize_observation
from profit_accounting_26.application.packaging_presentation import (
    normal_reminder,
    packaging_method_zh,
    packaging_summary,
    product_summary,
)
from profit_accounting_26.application.recognition_service import (
    RecognitionCancellation,
    RecognitionCancelledError,
    RecognitionResponseError,
    RecognitionService,
    RecognitionUnavailableError,
)
from profit_accounting_26.domain.models import (
    AIObservation,
    ImageType,
    PackagingProposal,
    PackagingScenario,
)
from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
from profit_accounting_26.ui.controllers.forwarder_cards_controller import ForwarderCardsController
from profit_accounting_26.ui.controllers.image_slots_controller import ImageSlotsController
from profit_accounting_26.ui.ui_loader import load_main_window
from profit_accounting_26.ui.widgets import Card, ImageSlotWidget, QuoteCard, confirm_action
from profit_accounting_26.ui.input_editing import install_blank_click_focus_filter


class RecognitionWorker(QObject):
    completed = Signal(object, object)
    failed = Signal(str, str)

    def __init__(self, service, image_items: list[dict[str, str]], cancellation: RecognitionCancellation, diagnostic_operation=None, user_context=None) -> None:
        super().__init__()
        self._service = service
        self._image_items = image_items
        self._cancellation = cancellation
        self._diagnostic_operation = diagnostic_operation
        self._user_context = user_context or {}

    @Slot()
    def run(self) -> None:
        try:
            observation, proposal = self._service.recognize(
                self._image_items,
                cancellation=self._cancellation,
                diagnostic_operation=self._diagnostic_operation,
                user_context=self._user_context,
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


class LocalReestimateWorker(QObject):
    completed = Signal(object)
    failed = Signal(str, str)

    def __init__(self, service, context: dict[str, Any]) -> None:
        super().__init__()
        self._service = service
        self._context = context

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(self._service.reestimate(**self._context))
        except RecognitionUnavailableError as exc:
            self.failed.emit("unavailable", str(exc))
        except RecognitionResponseError as exc:
            self.failed.emit("response", str(exc))
        except Exception as exc:
            self.failed.emit("failed", str(exc))


class _SpinAdapter(QObject):
    """让 .ui 的 QDoubleSpinBox 复用旧 LabeledSpin 的最小接口。

    提供 ``value()`` / ``setValue()`` / ``valueChanged`` / ``editingFinished``；
    程序化 ``setValue`` 不发射任何信号（等价旧版 _updating 保护）。
    """

    valueChanged = Signal(float)
    editingFinished = Signal()

    def __init__(self, spin: QDoubleSpinBox) -> None:
        super().__init__(spin)
        self.spin = spin
        self._programmatic = False
        spin.valueChanged.connect(self._on_value_changed)
        editor = spin.lineEdit()
        editor.installEventFilter(self)

    def _on_value_changed(self, value: float) -> None:
        if not self._programmatic:
            self.valueChanged.emit(value)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, value: float) -> None:
        self._programmatic = True
        try:
            self.spin.setValue(float(value))
        finally:
            self._programmatic = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.FocusOut and not self._programmatic:
            self.editingFinished.emit()
        return False


class _TextAdapter(QObject):
    """QLineEdit / QTextEdit 统一文本接口（text/setText/clear/textChanged）。"""

    textChanged = Signal(str)

    def __init__(self, widget) -> None:
        super().__init__(widget)
        self._widget = widget
        self._programmatic = False
        if isinstance(widget, QTextEdit):
            widget.textChanged.connect(self._on_changed)
        else:
            widget.textChanged.connect(self._on_changed)

    def _on_changed(self, *args) -> None:
        if not self._programmatic:
            self.textChanged.emit(self.text())

    def text(self) -> str:
        if isinstance(self._widget, QTextEdit):
            return self._widget.toPlainText()
        return self._widget.text()

    def setText(self, value: str) -> None:
        self._programmatic = True
        try:
            if isinstance(self._widget, QTextEdit):
                self._widget.setPlainText(value)
            else:
                self._widget.setText(value)
        finally:
            self._programmatic = False

    def clear(self) -> None:
        self.setText("")


class _UserCorrectionEdit(QTextEdit):
    """带“示例文字层”的用户修正输入框。

    QTextEdit 原生 placeholder 在 Windows 上按单行绘制且不换行，长示例显示不全；
    这里改为 viewport 内的只读 QLabel 示例层：内容为空时显示、有真实输入时隐藏。
    示例绝不出现在 toPlainText()，不写入 user_note，不触发校准 dirty。
    """

    EXAMPLE_TEXT = (
        "在此填写用于重估的修正\n"
        "例如：这个睡帽可以压缩后发货"
    )
    MIN_HEIGHT = 68
    MAX_HEIGHT = 88

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mirror_widget: QTextEdit | None = None
        self.example = QLabel(self.EXAMPLE_TEXT, self.viewport())
        self.example.setWordWrap(True)
        self.example.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.example.setProperty("muted", True)
        self.example.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.example.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.example.setStyleSheet("background: transparent;")
        self.setAcceptRichText(False)
        self.viewport().installEventFilter(self)
        self.textChanged.connect(self._sync_example)
        self._sync_example()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self._layout_example()
        return super().eventFilter(watched, event)

    def _sync_example(self) -> None:
        """内容为空显示示例，有真实输入立即隐藏；程序化 setText/clear 同样生效。"""
        self.example.setVisible(not self.toPlainText())
        self._layout_example()

    def _layout_example(self) -> None:
        viewport = self.viewport()
        width = max(40, viewport.width() - 22)
        self.example.setGeometry(10, 7, width, max(0, viewport.height() - 14))
        needed = self.example.heightForWidth(width)
        target = min(max(self.MIN_HEIGHT, 7 + needed + 9), self.MAX_HEIGHT)
        if self.height() != target:
            self.setFixedHeight(target)
        if self.mirror_widget is not None and self.mirror_widget.height() != target:
            self.mirror_widget.setFixedHeight(target)
        self.example.setGeometry(10, 7, width, max(0, self.height() - 14))


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
        self.session = CalculationSession()
        self.record_id: str | None = None
        self.dirty = False
        self.packaging_stale = False
        self._updating = False
        self.current_quote = None
        self.current_forwarder = None
        self.current_system_cost: float | None = None
        self.selected_profit_rule_id = str(self.settings.get("selected_profit_rule_id") or "")
        self.package_selection_changed = False
        self.manual_scenarios: set[str] = set()
        self._recognition_thread: QThread | None = None
        self._recognition_worker: RecognitionWorker | None = None
        self._recognition_cancellation: RecognitionCancellation | None = None
        self._recognition_dialog: QDialog | None = None
        self._local_thread: QThread | None = None
        self._local_worker: LocalReestimateWorker | None = None
        self._local_dialog: QDialog | None = None
        self._ai_baseline: dict[str, Any] | None = None
        self.initial_ai_snapshot: dict[str, Any] | None = None
        self.current_feedback_id: str | None = None
        # 历史编辑模式：load_record_payload 进入，清空并新建退出；
        # 编辑模式下任何字段修改都允许直接重算并更新同一条记录。
        self.editing_record_id: str | None = None
        # 用户校准 dirty：仅用户手动修改当前采用尺寸/重量或填写用户修正时置位；
        # AI 首次自动复制不置位（程序化 setValue 不发信号）。
        self.user_calibration_dirty = False
        self._recognized_image_fingerprint: tuple[tuple[str, str], ...] = ()
        self._accepted_bare_fields: set[str] = set()
        self._pending_confirmed_normal: dict[str, Any] = {}

        self._load_ui_widgets()
        self._build_dynamic_regions()
        self._connect_calculation_signals()

        # 图片框管理委托 ImageSlotsController（第一阶段 Controller 拆分）；
        # AI 状态回调 _image_changed 保留在本页，行为不变。
        # settings 以 provider 注入：refresh_settings 会用新 dict 整体替换
        # self.settings，Controller 不得持有固定 dict 引用，也不得自行
        # load() 创建第二份缓存；settings 唯一当前状态仍由本页持有。
        self.image_slots_controller = ImageSlotsController(
            self._root,
            self,
            self.context.settings_service,
            settings_provider=lambda: self.settings,
            image_changed_callback=self._image_changed,
            mark_dirty_callback=self._mark_dirty,
        )

        # 动态货代卡与货代选择状态委托 ForwarderCardsController（第二阶段
        # Controller 拆分）；settings 同样以 provider 注入，语义与
        # ImageSlotsController 完全一致。quote_insert_index 的定义仍由
        # _build_dynamic_regions 持有，此处只传入插入位置。
        self.forwarder_cards_controller = ForwarderCardsController(
            self._root,
            self.context.settings_service,
            settings_provider=lambda: self.settings,
            insert_index=self.quote_insert_index,
            selected_forwarder_id=str(self.settings.get("selected_forwarder_id") or ""),
            mark_dirty_callback=self._mark_dirty,
            recalculate_callback=self.recalculate,
        )

        # 利润区委托 CalculationBinder（双场景 driver 状态机）
        self.profit_binder = CalculationBinder(self._root, context)
        self.profit_binder.set_exchange_rate(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        self.profit_binder.set_selected_rule_id(self.selected_profit_rule_id)
        self.profit_binder.set_rules(tuple(
            rule for rule in self.context.settings_service.rules_from_settings(self.settings)
            if rule.enabled and not rule.archived
        ))
        self.profit_binder.selectedRuleChanged.connect(self._persist_selected_rule)

        self.rebuild_image_slots(int(self.settings.get("image_slot_count", 5)))
        self.rebuild_quote_cards()
        # 页面初始化：执行一次 USD → RMB 同步（RMB=USD×汇率）
        self._sync_tail_rmb_from_usd(recalculate=False)
        self.recalculate()
        self._blank_focus_guard = install_blank_click_focus_filter(self)

    # ------------------------------------------------------------------
    # .ui 加载与控件绑定
    # ------------------------------------------------------------------

    def _load_ui_widgets(self) -> None:
        """加载冻结 main_window.ui，取 pageCalculation 并接管为本页布局。"""
        self._ui_root = load_main_window()
        root = self._ui_root.findChild(QWidget, "pageCalculation")
        if root is None:
            raise RuntimeError("main_window.ui 缺少 pageCalculation")
        root.setParent(self)
        root.setVisible(True)  # setParent 会清除可见标记，必须显式恢复
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(root)
        self._root = root

        f = root.findChild
        # 图片区（图片框重建/增减/保存配置由 ImageSlotsController 按
        # objectName 绑定；此处只保留属于识图状态的 AI识图按钮）
        self.ai_button = f(QPushButton, "btnAiRecognize")
        # AI 摘要区
        self.product_summary = _TextAdapter(f(QLineEdit, "txtAiSummary"))
        self.structure_summary = _TextAdapter(f(QLineEdit, "txtPackingState"))
        self.structure_summary._widget.setReadOnly(True)
        self.btn_partial_reestimate = f(QPushButton, "btnPartialReestimate")
        self.btn_partial_reestimate.setText("按修正重估")
        ai_layout = f(QGridLayout, "aiSummaryLayout")
        # 该字段仅保存 AI 材质事实，不再作为摘要卡的隐藏第二行。
        # 保留 parent 以维持现有数据绑定和生命周期。
        self.material_summary = QLineEdit(root)
        self.material_summary.setVisible(False)
        self.review_badge = QLabel("待识别")
        self.review_badge.setObjectName("lblReviewBadge")
        self.review_badge.setProperty("warning", True)
        if ai_layout is not None:
            summary_title = f(QLabel, "lblAiSummaryTitle")
            if summary_title is not None:
                # 状态与标题共享既有标题行，不再为 badge 增加一整行高度。
                ai_layout.removeWidget(summary_title)
                summary_header = QWidget()
                summary_header.setObjectName("aiSummaryHeader")
                summary_header_layout = QHBoxLayout(summary_header)
                summary_header_layout.setContentsMargins(0, 0, 0, 0)
                summary_header_layout.setSpacing(5)
                summary_header_layout.addWidget(summary_title)
                summary_header_layout.addWidget(self.review_badge)
                summary_header_layout.addStretch(1)
                ai_layout.addWidget(summary_header, 0, 0)
        # 成本与裸尺寸
        self.product_cost = self._cost_spin("spinProductCostRmb", maximum=1_000_000)
        self.domestic_shipping = self._cost_spin("spinDomesticFreightRmb", maximum=1_000_000)
        self.bare_length = self._dim_spin("spinBareLengthCm")
        self.bare_width = self._dim_spin("spinBareWidthCm")
        self.bare_height = self._dim_spin("spinBareHeightCm")
        self.bare_weight = self._weight_spin("spinBareWeightG")
        # AI估算（原正常档位置）：第一次 AI 结果，全部只读，不参与正式计算
        self.normal_fields: dict[str, Any] = {
            "name": "AI估算",
            "card": f(QWidget, "normalPackageCard"),
            "radio": f(QRadioButton, "radioNormalPackage"),
            "method": _TextAdapter(f(QTextEdit, "txtNormalReminder")),
            "length": self._dim_spin("spinNormalLengthCm"),
            "width": self._dim_spin("spinNormalWidthCm"),
            "height": self._dim_spin("spinNormalHeightCm"),
            "weight": self._weight_spin("spinNormalWeightG"),
        }
        # 当前采用（原保守档位置）：唯一正式包装输入，用户可手动修正
        self.conservative_fields: dict[str, Any] = {
            "name": "当前采用",
            "card": f(QWidget, "conservativePackageCard"),
            "radio": f(QRadioButton, "radioConservativePackage"),
            "method": _TextAdapter(f(QLineEdit, "txtConservativeMethod")),
            "length": self._dim_spin("spinConservativeLengthCm"),
            "width": self._dim_spin("spinConservativeWidthCm"),
            "height": self._dim_spin("spinConservativeHeightCm"),
            "weight": self._weight_spin("spinConservativeWeightG"),
        }
        # 尾程费用
        self.tail_fee_usd = self._cost_spin("spinTailFreightUsd", maximum=100_000)
        self.tail_fee_rmb = self._cost_spin("spinTailFreightRmb", maximum=1_000_000)
        self.tail_fee_usd.setValue(float(self.settings.get("default_tail_fee_usd", 5.56)))
        self.tail_fee_rmb.setValue(float(self.settings.get("default_tail_fee_rmb", 40.0)))
        self.forwarder_cards_layout = f(QHBoxLayout, "forwarderCardsLayout")
        # 系统成本
        self.btn_system_calculate = f(QPushButton, "btnSystemCalculate")
        self.system_rows: dict[str, QLabel] = {
            # 六行固定排版：采购成本 / 国内运费 / 头程 / 服务费 / 尾程 / 总成本
            "product": f(QLabel, "lblSystemCostValue0"),
            "domestic": f(QLabel, "lblSystemCostValue1"),
            "first_mile": f(QLabel, "lblSystemCostValue2"),
            "service": f(QLabel, "lblSystemCostValue3"),
            "tail": f(QLabel, "lblSystemCostValue6"),
        }
        self.system_total = f(QLabel, "lblSystemTotalRmb")
        self.system_total_usd = f(QLabel, "lblSystemTotalUsd")
        # 系统成本名称列（与 system_rows 一一对应）
        self.system_names: dict[str, QLabel] = {
            "product": f(QLabel, "lblSystemCostName0"),
            "domestic": f(QLabel, "lblSystemCostName1"),
            "first_mile": f(QLabel, "lblSystemCostName2"),
            "service": f(QLabel, "lblSystemCostName3"),
            "tail": f(QLabel, "lblSystemCostName6"),
        }
        # 底部
        self.product_link = f(QLineEdit, "txtProductLink")
        self.btn_save_record = f(QPushButton, "btnSaveCurrentRecord")
        self.btn_clear_new = f(QPushButton, "btnClearAndNew")
        # 保存按钮旁的历史编辑状态轻提示（不占用新布局区域）
        bottom_layout = f(QHBoxLayout, "bottomActionLayout")
        self.edit_state_label = QLabel("")
        self.edit_state_label.setProperty("muted", True)
        self.edit_state_label.setVisible(False)
        if bottom_layout is not None:
            bottom_layout.insertWidget(2, self.edit_state_label)
        self._apply_adopted_flow_ui()
        self._apply_round3_ui_polish()

    def _cost_spin(self, name: str, *, maximum: float) -> _SpinAdapter:
        spin = self._root.findChild(QDoubleSpinBox, name)
        spin.setRange(0.0, maximum)
        spin.setDecimals(2)
        return _SpinAdapter(spin)

    def _dim_spin(self, name: str) -> _SpinAdapter:
        spin = self._root.findChild(QDoubleSpinBox, name)
        spin.setRange(0.0, 500.0)
        spin.setDecimals(1)
        return _SpinAdapter(spin)

    def _weight_spin(self, name: str) -> _SpinAdapter:
        spin = self._root.findChild(QDoubleSpinBox, name)
        spin.setRange(0.0, 100_000.0)
        spin.setDecimals(1)
        return _SpinAdapter(spin)

    def _apply_adopted_flow_ui(self) -> None:
        """把双档收敛为 AI估算 / 当前采用：两张卡视觉镜像（同一行序、行高与宽度）。

        不改变主界面左右布局，只复用现有两个包装卡的位置；
        旧 normal/conservative 控件与数据字段保留兼容。
        """
        f = self._root.findChild
        # 1) 隐藏旧选档 radio
        for fields in (self.normal_fields, self.conservative_fields):
            radio = fields.get("radio")
            if radio is not None:
                radio.setVisible(False)
        # 2) 重排两张卡为相同行结构：标题+行内副标题 / 包装尺寸 / 长宽高 / 包装后重量 / 底部多行框
        for fields, subtitle_text in (
            (self.normal_fields, "第一次 AI 估算结果 · 只读"),
            (self.conservative_fields, "用户可手动修正"),
        ):
            card = fields["card"]
            grid = card.layout()
            if not isinstance(grid, QGridLayout):
                continue
            is_ai = fields is self.normal_fields
            prefix = "Normal" if is_ai else "Conservative"
            dims_label = f(QLabel, f"lbl{prefix}Dims")
            weight_label = f(QLabel, f"lbl{prefix}Weight")
            length_row = f(QHBoxLayout, f"layout_spin{prefix}LengthCm")
            width_row = f(QHBoxLayout, f"layout_spin{prefix}WidthCm")
            height_row = f(QHBoxLayout, f"layout_spin{prefix}HeightCm")
            weight_row = f(QHBoxLayout, f"layout_spin{prefix}WeightG")
            method_widget = fields["method"]._widget
            # 先清空网格再按统一行序重建（控件对象复用，引用不失效）
            while grid.count():
                grid.takeAt(0)
            # 行 0：标题 + 行内副标题（释放原副标题独立行）
            header_box = QWidget()
            header_row = QHBoxLayout(header_box)
            header_row.setContentsMargins(0, 0, 0, 0)
            header_row.setSpacing(6)
            title_label = QLabel(str(fields["name"]))
            title_label.setStyleSheet("font-weight: 600;")
            subtitle = QLabel(subtitle_text)
            font = subtitle.font()
            if font.pointSize() > 8:
                font.setPointSize(font.pointSize() - 1)
            subtitle.setFont(font)
            subtitle.setProperty("hint", True)
            header_row.addWidget(title_label)
            header_row.addWidget(subtitle)
            header_row.addStretch(1)
            grid.addWidget(header_box, 0, 0, 1, 3)
            # 行 1：包装尺寸
            if dims_label is not None:
                grid.addWidget(dims_label, 1, 0, 1, 3)
            # 行 2：长 / 宽 / 高
            if length_row is not None:
                grid.addLayout(length_row, 2, 0)
            if width_row is not None:
                grid.addLayout(width_row, 2, 1)
            if height_row is not None:
                grid.addLayout(height_row, 2, 2)
            # 行 3：包装后重量 —— [标题][10px][固定宽输入框][5px][g][stretch] 单行紧凑结构
            if weight_row is not None:
                weight_row.setSpacing(5)
            weight_hbox = QHBoxLayout()
            weight_hbox.setContentsMargins(0, 0, 0, 0)
            weight_hbox.setSpacing(10)
            if weight_label is not None:
                weight_hbox.addWidget(weight_label)
            if weight_row is not None:
                weight_hbox.addLayout(weight_row)
            grid.addLayout(weight_hbox, 3, 0, 1, 3)
            # 行 4/5：底部区域
            # AI估算：包装方式标签 + 只读多行框（保持原样）
            # 当前采用：用户修正多行框直接放在包装后重量下一行（无独立“用户修正”小标题）
            #          + 最底部“真实头程（选填）”一行
            if is_ai:
                bottom_label = QLabel("包装方式")
                bottom_label.setFixedHeight(20)
                grid.addWidget(bottom_label, 4, 0, 1, 3)
                note_edit = method_widget
                note_edit.setReadOnly(True)
                note_edit.setPlaceholderText("AI估算包装方式（第一次 AI 结果，只读）")
                if not isinstance(note_edit, _UserCorrectionEdit):
                    note_edit.setFixedHeight(104)
                note_edit.setMinimumWidth(90)
                note_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                note_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                note_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                note_edit.setAcceptRichText(False)
                grid.addWidget(note_edit, 5, 0, 1, 3)
            else:
                note_edit = _UserCorrectionEdit()
                self.user_correction = _TextAdapter(note_edit)
                note_edit.setMinimumWidth(90)
                note_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                note_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                note_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
                note_edit.setAcceptRichText(False)
                grid.addWidget(note_edit, 4, 0, 1, 3)
                self._build_actual_first_mile_row(grid, 5)
        if not hasattr(self, "user_correction"):  # 防御：布局缺失时仍保证字段可用
            self.user_correction = _TextAdapter(QTextEdit())
        self.user_correction.textChanged.connect(lambda _text: self._user_calibration_changed())
        if not hasattr(self, "actual_first_mile_fee_edit"):  # 防御：布局缺失时仍保证字段可用
            self.actual_forwarder_combo = QComboBox()
            self.actual_first_mile_fee_edit = QLineEdit()
            self._reload_actual_forwarder_combo()
        # 示例层与左卡“包装方式”框镜像同高（随 viewport 宽度重算）
        right_bottom = self.user_correction._widget
        left_bottom = self.normal_fields["method"]._widget
        if isinstance(right_bottom, _UserCorrectionEdit):
            right_bottom.mirror_widget = left_bottom
            right_bottom._layout_example()
        # 3) 左卡 AI估算全部只读；右卡 当前采用全部可编辑；旧方法输入行隐藏
        for key in ("length", "width", "height", "weight"):
            self.normal_fields[key].spin.setReadOnly(True)
        for key in ("length", "width", "height", "weight"):
            spin = self.conservative_fields[key].spin
            spin.setReadOnly(False)
            spin.setProperty("preview", False)
            spin.style().unpolish(spin)
            spin.style().polish(spin)
        method_edit = self.conservative_fields["method"]._widget
        method_edit.setReadOnly(False)
        method_edit.setVisible(False)
        method_label = f(QLabel, "lblConservativeMethod")
        if method_label is not None:
            method_label.setVisible(False)
        conservative_card = self.conservative_fields["card"]
        conservative_card.setProperty("frozen", False)
        conservative_card.style().unpolish(conservative_card)
        conservative_card.style().polish(conservative_card)
        self._style_card(self.normal_fields, selected=False)
        self._style_card(self.conservative_fields, selected=True)
        # 4) 系统成本卡固定六行：采购成本 / 国内运费 / 头程（货代名）/ 服务费 / 尾程 / 总成本；
        # 标签与金额对齐由静态 main_window.ui 排版完成，旧的重量/计费重/物流总价行已删除

    def _apply_round3_ui_polish(self) -> None:
        """利润区规则状态放字段标题上方（尾程输入已在 main_window.ui 静态独立卡内）。

        只移动既有控件，不改任何计算逻辑与算法。
        """
        f = self._root.findChild
        # 利润区规则状态放字段标题上方；字号用 QFont（binder 用 setStyleSheet 只覆盖颜色）
        profit_grid = f(QGridLayout, "profitFieldsGrid")
        if profit_grid is not None:
            for layout_name in ("layoutNoActivityProfitTitle", "layoutActivityProfitTitle"):
                hbox = f(QHBoxLayout, layout_name)
                if hbox is None or hbox.count() < 2:
                    continue
                index = profit_grid.indexOf(hbox)
                if index < 0:
                    continue
                row, col, row_span, col_span = profit_grid.getItemPosition(index)
                # 先取出控件再移除空布局：removeItem 会删除无主的子布局对象
                title_widget = hbox.takeAt(0).widget()
                status_widget = hbox.takeAt(0).widget()
                profit_grid.removeItem(hbox)
                if status_widget is not None:
                    status_font = status_widget.font()
                    if status_font.pointSize() > 8:
                        status_font.setPointSize(status_font.pointSize() - 1)
                    status_widget.setFont(status_font)
                stack = QVBoxLayout()
                stack.setContentsMargins(0, 0, 0, 0)
                stack.setSpacing(1)
                if status_widget is not None:
                    stack.addWidget(status_widget)
                if title_widget is not None:
                    stack.addWidget(title_widget)
                profit_grid.addLayout(stack, row, col, row_span, col_span)
        # 此结论仅重复利润区标题提示，且在紧凑窗口中占用无效的独立行。
        # 计算与字段布局完全不依赖它，因此隐藏该显示冗余项。
        profit_conclusion = f(QLabel, "lblProfitConclusion")
        if profit_conclusion is not None:
            profit_conclusion.setVisible(False)

    def _build_dynamic_regions(self) -> None:
        """清除 Designer 预览控件，准备动态图片框与货代卡片容器。"""
        # 图片预览卡片（imageCard1..5）
        for index in range(1, 6):
            card = self._root.findChild(QWidget, f"imageCard{index}")
            if card is not None:
                card.setParent(None)
                card.deleteLater()
        # 货代预览卡片（深圳 / 义乌）
        for name in ("forwarderCardShenzhen", "forwarderCardYiwu"):
            card = self._root.findChild(QWidget, name)
            if card is not None:
                card.setParent(None)
                card.deleteLater()
        # 动态货代卡片插在保守档之后、系统成本卡之前（0:裸尺寸 1:正常 2:保守 [3..]:货代 末:系统）
        self.quote_insert_index = 3
        # 隐藏的内部结构选项（确定性包装规则仍需要）
        self._build_hidden_structure_widgets()

    def _build_hidden_structure_widgets(self) -> None:
        """软硬/折叠/压缩与硬结构选项不直接展示，仅作为观察数据结构。"""
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
            self.structure_checks[key] = QCheckBox(text)
        container = QWidget()
        container.setVisible(False)
        holder_layout = QHBoxLayout(container)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        for widget in (
            self.rigidity_combo,
            self.foldability_combo,
            self.compressibility_combo,
            *self.structure_checks.values(),
        ):
            widget.setParent(container)
            holder_layout.addWidget(widget)
        ai_layout = self._root.findChild(QGridLayout, "aiSummaryLayout")
        if ai_layout is not None:
            ai_layout.addWidget(container, 2, 0, 1, 5)

    def _connect_calculation_signals(self) -> None:
        for widget in (self.product_cost, self.domestic_shipping, self.tail_fee_usd, self.tail_fee_rmb):
            widget.valueChanged.connect(lambda _value: self._mark_dirty())
        # 商品成本 / 国内运费实时联动：修改后立即重算唯一总成本，不等编辑完成
        self.product_cost.valueChanged.connect(lambda _value: self.recalculate())
        self.domestic_shipping.valueChanged.connect(lambda _value: self.recalculate())
        self.product_link.textChanged.connect(lambda _text: self._mark_dirty())

        for name, fields in (("AI估算", self.normal_fields), ("当前采用", self.conservative_fields)):
            fields["method"].textChanged.connect(lambda _text, n=name: self._scenario_manually_changed(n))
            for key in ("length", "width", "height", "weight"):
                fields[key].valueChanged.connect(lambda _value, n=name: self._scenario_manually_changed(n))

        self.product_cost.editingFinished.connect(lambda: self._accept_numeric_field("product_cost_rmb", self.product_cost))
        self.domestic_shipping.editingFinished.connect(lambda: self._accept_numeric_field("domestic_shipping_rmb", self.domestic_shipping))
        for widget in (self.bare_length, self.bare_width, self.bare_height, self.bare_weight):
            widget.editingFinished.connect(self._upstream_changed)
        for key, widget in (("length_cm", self.bare_length), ("width_cm", self.bare_width), ("height_cm", self.bare_height), ("weight_g", self.bare_weight)):
            widget.editingFinished.connect(lambda k=key: self._accept_bare_field(k))
        self.product_summary.textChanged.connect(lambda _text: self._upstream_changed())
        self.product_summary._widget.editingFinished.connect(
            lambda: self._accept_text_field("product_name", self.product_summary)
        )
        self.material_summary.textChanged.connect(lambda _text: self._upstream_changed())
        self.structure_summary.textChanged.connect(lambda _text: self._upstream_changed())
        for combo in (self.rigidity_combo, self.foldability_combo, self.compressibility_combo):
            combo.currentIndexChanged.connect(lambda _index: self._upstream_changed())
        for key, box in self.structure_checks.items():
            if key == "no_hard_structure":
                box.toggled.connect(self._on_no_structure_toggled)
            else:
                box.toggled.connect(lambda checked, k=key: self._on_structure_toggled(k, checked))
        self.tail_fee_rmb.editingFinished.connect(self._tail_rmb_changed)
        self.tail_fee_usd.editingFinished.connect(self._tail_usd_changed)
        # 尾程 USD 实时联动：直接连接真实 USD 控件的 valueChanged，不等待编辑完成
        self.tail_fee_usd.valueChanged.connect(self._tail_usd_live_changed)
        # 真实头程仅作为 actual_logistics 保存；它仍属于未保存修改，
        # 但不能影响 user_calibration_dirty。
        self.actual_first_mile_fee_edit.textChanged.connect(self._actual_first_mile_changed)
        self.actual_forwarder_combo.currentTextChanged.connect(self._actual_first_mile_changed)

        self.ai_button.clicked.connect(self.run_recognition)
        self.btn_partial_reestimate.clicked.connect(self.reestimate_packaging)
        self.btn_system_calculate.clicked.connect(self.recalculate)
        self.btn_save_record.clicked.connect(self.save_record)
        self.btn_clear_new.clicked.connect(self.clear_new)

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

    # ------------------------------------------------------------------
    # 状态辅助
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
            self.dirtyChanged.emit(True)

    def _actual_first_mile_changed(self, *_args: Any) -> None:
        """真实头程改动只进入通用未保存状态，不是用户包装校准。"""
        if not self._updating:
            self._mark_dirty()

    def _adopt_packaging(self, proposal: PackagingProposal) -> None:
        """Keep one packaging authority for page, calculation, persistence and logs."""
        self.proposal = proposal  # legacy UI alias; never independently calculated
        self.session.adopt(proposal)

    def _adopted_packaging(self) -> PackagingProposal | None:
        return self.session.adopted_packaging or self.proposal

    def mark_saved(self) -> None:
        self.dirty = False
        self.dirtyChanged.emit(False)

    def _persist_selected_rule(self, rule_id: str) -> None:
        self.selected_profit_rule_id = str(rule_id or "")
        self.settings["selected_profit_rule_id"] = self.selected_profit_rule_id
        self.context.settings_service.save(self.settings)
        self._mark_dirty()

    def set_exchange_rate(self, rate: float) -> None:
        """主窗口汇率保存后同步利润区冻结换算。"""
        self.settings = self.context.settings_service.load()
        self.profit_binder.set_exchange_rate(float(rate))

    # ------------------------------------------------------------------
    # 图片框（委托 ImageSlotsController；保留原调用表面）
    # ------------------------------------------------------------------

    @property
    def image_slots(self) -> list[ImageSlotWidget]:
        return self.image_slots_controller.image_slots

    def rebuild_image_slots(self, count: int) -> None:
        return self.image_slots_controller.rebuild_image_slots(count)

    def change_slot_count(self, delta: int) -> None:
        return self.image_slots_controller.change_slot_count(delta)

    def save_image_config(self) -> None:
        return self.image_slots_controller.save_image_config()

    def remove_image(self, index: int) -> None:
        return self.image_slots_controller.remove_image(index)

    def _image_fingerprint(self) -> tuple[tuple[str, str], ...]:
        return self.image_slots_controller.image_fingerprint()

    def paste_from_clipboard(self) -> bool:
        return self.image_slots_controller.paste_from_clipboard()

    # ------------------------------------------------------------------
    # 货代卡兼容代理（状态由 ForwarderCardsController 持有）
    # ------------------------------------------------------------------

    @property
    def quote_cards(self) -> dict[str, QuoteCard]:
        return self.forwarder_cards_controller.quote_cards

    @property
    def selected_forwarder_id(self) -> str:
        return self.forwarder_cards_controller.selected_forwarder_id

    @selected_forwarder_id.setter
    def selected_forwarder_id(self, value: str) -> None:
        self.forwarder_cards_controller.selected_forwarder_id = str(value)

    @property
    def forwarder_selection_changed(self) -> bool:
        return self.forwarder_cards_controller.forwarder_selection_changed

    @forwarder_selection_changed.setter
    def forwarder_selection_changed(self, value: bool) -> None:
        self.forwarder_cards_controller.forwarder_selection_changed = bool(value)

    def rebuild_quote_cards(self) -> None:
        return self.forwarder_cards_controller.rebuild_quote_cards()

    def select_forwarder(self, forwarder_id: str) -> None:
        return self.forwarder_cards_controller.select_forwarder(forwarder_id)

    def _image_changed(self) -> None:
        self._mark_dirty()
        if self._ai_baseline is not None and self._image_fingerprint() != self._recognized_image_fingerprint:
            self.ai_button.setText("AI整体重估")
            self.ai_button.setEnabled(self._recognition_thread is None)
        elif self._ai_baseline is None:
            self.ai_button.setText("AI识图")
            self.ai_button.setEnabled(self._recognition_thread is None)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Paste) and self.paste_from_clipboard():
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 观察数据
    # ------------------------------------------------------------------

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @staticmethod
    def _observation_structure_summary(observation: AIObservation) -> str:
        parts = [observation.material] if observation.material else []
        labels = {
            "soft": "柔软", "semi_rigid": "半硬", "hard": "硬质",
            "good": "可折叠", "limited": "有限折叠", "none": "不可折叠",
        }
        for value in (observation.rigidity, observation.foldability, observation.compressibility):
            if label := labels.get(value):
                parts.append(label)
        for enabled, label in (
            (observation.has_hard_bottom, "硬底"), (observation.has_hard_backboard, "硬背板"),
            (observation.has_frame, "框架"), (observation.has_rigid_insert, "硬内衬"),
            (observation.requires_shape_retention, "保形"), (observation.retail_box_visible, "原盒"),
        ):
            if enabled is True:
                parts.append(label)
        return "；".join(dict.fromkeys(parts))

    def _accept_bare_field(self, key: str) -> None:
        if not self._updating:
            self._accepted_bare_fields.add(key)
            widgets = {
                "length_cm": self.bare_length, "width_cm": self.bare_width,
                "height_cm": self.bare_height, "weight_g": self.bare_weight,
            }
            self._accept_numeric_field(key, widgets[key])

    def _accept_numeric_field(self, key: str, widget: Any) -> None:
        if self._updating:
            return
        value = widget.value()
        # 金额字段 0 是合法数值（样品/赠品、免运费），只有尺寸/重量仍把 0 视为未填写
        if key in ("product_cost_rmb", "domestic_shipping_rmb"):
            self.session.confirm_value(key, value)
        else:
            self.session.confirm_value(key, value if value > 0 else None)
        self.recalculate()

    def _accept_text_field(self, key: str, widget: _TextAdapter) -> None:
        if self._updating:
            return
        self.session.confirm_value(key, widget.text().strip() or None)

    def _confirmed_facts(self) -> dict[str, dict[str, Any]]:
        facts = self.session.confirmed_facts()
        if "正常档" in self.manual_scenarios:
            normal = self._scenario_data(self.normal_fields)
            if all(normal.get(key) for key in ("length_cm", "width_cm", "height_cm", "weight_g")):
                facts["normal_packaging"] = {
                    "value": normal, "source": "user_confirmed", "meaning": "confirmed normal packaged dimensions and weight",
                }
        return facts

    def _restore_confirmed_normal(self, proposal: PackagingProposal) -> None:
        normal = self._pending_confirmed_normal
        if not normal:
            return
        for field in ("length_cm", "width_cm", "height_cm", "weight_g"):
            value = normal.get(field)
            if value:
                setattr(proposal.normal, field, float(value))
                if float(getattr(proposal.conservative, field) or 0) < float(value):
                    setattr(proposal.conservative, field, float(value))
        proposal.normal.confidence = "high"
        proposal.normal.needs_review = False
        proposal.review_reasons.append("user confirmed normal packaging retained")

    def _apply_observation(self, observation: AIObservation) -> None:
        previous_updating = self._updating
        self._updating = True
        if observation.product_name or observation.product_type:
            self.product_summary.setText(product_summary(observation))
        if observation.material:
            self.material_summary.setText(observation.material)
        self.structure_summary.setText(observation.display_packaging_summary or self._observation_structure_summary(observation))
        self._set_combo_data(self.rigidity_combo, observation.rigidity)
        self._set_combo_data(self.foldability_combo, observation.foldability)
        self._set_combo_data(self.compressibility_combo, observation.compressibility)
        if observation.product_cost_rmb is not None and "product_cost_rmb" not in self.session.user_overrides:
            self.product_cost.setValue(observation.product_cost_rmb)
        if observation.domestic_shipping_rmb is not None and "domestic_shipping_rmb" not in self.session.user_overrides:
            self.domestic_shipping.setValue(observation.domestic_shipping_rmb)
        if observation.length_cm is not None and "length_cm" not in self.session.user_overrides:
            self.bare_length.setValue(observation.length_cm)
        if observation.width_cm is not None and "width_cm" not in self.session.user_overrides:
            self.bare_width.setValue(observation.width_cm)
        if observation.height_cm is not None and "height_cm" not in self.session.user_overrides:
            self.bare_height.setValue(observation.height_cm)
        if observation.weight_g is not None and "weight_g" not in self.session.user_overrides:
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

    def _refresh_display_summaries(self, observation: AIObservation, proposal: PackagingProposal) -> None:
        previous_updating = self._updating
        self._updating = True
        self.product_summary.setText(product_summary(observation))
        self.structure_summary.setText(packaging_summary(observation, proposal))
        self._updating = previous_updating

    # ------------------------------------------------------------------
    # AI 识图
    # ------------------------------------------------------------------

    def run_recognition(self) -> None:
        if self._recognition_thread is not None:
            return
        image_items = [
            {"path": str(slot.path)}
            for slot in self.image_slots
            if slot.path
        ]
        if not image_items:
            QMessageBox.information(self, "没有图片", "请先导入至少一张图片。")
            return
        self._diagnostic_operation = self.context.diagnostic_logger.begin_operation("ai-recognition")
        images = [self.context.diagnostic_logger.image_metadata(item["path"]) for item in image_items]
        self._diagnostic_operation.event("image_attached", images=images)
        confirmed_facts = self._confirmed_facts()
        self._diagnostic_operation.event("user_confirmed_facts", confirmed_facts=confirmed_facts)
        self._diagnostic_operation.event("ai_request_started")
        self._show_recognition_dialog()
        self.ai_button.setEnabled(False)
        self._recognition_cancellation = RecognitionCancellation()
        self._pending_confirmed_normal = self._scenario_data(self.normal_fields) if "正常档" in self.manual_scenarios else {}
        self._recognition_thread = QThread(self)
        self._recognition_worker = RecognitionWorker(
            self.context.recognition_service,
            image_items,
            self._recognition_cancellation,
            self._diagnostic_operation,
            confirmed_facts,
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

    # ------------------------------------------------------------------
    # 第一次 AI 初始快照（History V2 ai_initial 唯一来源）
    # ------------------------------------------------------------------

    def _capture_initial_ai_snapshot(
        self,
        observation: AIObservation,
        external_proposal: PackagingProposal | None,
    ) -> dict[str, Any]:
        """第一次完整视觉识图成功后捕获 AI 初始快照；无法可靠获得的字段不写、不猜。"""
        adopted = self._adopted_packaging()
        metadata_proposal = adopted or external_proposal
        provider = None
        try:
            bound = self.context.api_profile_store.bound_profile(VISUAL_AI)
            if bound:
                profile, _ = bound
                provider = getattr(profile, "provider", None)
        except Exception:
            provider = None
        return {
            "provider": str(provider).strip() or None,
            "model": observation.model or None,
            "prompt_version": observation.prompt_version or None,
            "engine_version": metadata_proposal.engine_version if metadata_proposal else "vision-runtime-v1",
            "calibration_version": metadata_proposal.calibration_version if metadata_proposal else "",
            "observation": observation.to_dict(),
            "external_ai_packaging_proposal": external_proposal.to_dict() if external_proposal else None,
            "adopted_packaging": adopted.to_dict() if adopted else None,
        }

    def _maybe_capture_initial_ai_snapshot(
        self,
        observation: AIObservation,
        external_proposal: PackagingProposal | None,
    ) -> None:
        """只在 snapshot 尚不存在时捕获；第二次识图/按修正重估/人工修改均不得覆盖。"""
        if self.initial_ai_snapshot is None:
            self.initial_ai_snapshot = self._capture_initial_ai_snapshot(observation, external_proposal)

    @Slot(object, object)
    def _recognition_completed(self, observation: AIObservation, external_proposal: PackagingProposal | None) -> None:
        is_first_visual_result = self.initial_ai_snapshot is None
        conflicts = self.session.protect_confirmed_values(observation)
        self.session.ai_raw_response = observation.raw_payload
        self.session.ai_raw_observation = dict(observation.raw_payload.get("observation") or {})
        self.session.normalized_observation = observation
        self.session.money_candidates = list(observation.raw_payload.get("money_candidates") or [])
        if is_first_visual_result:
            self.session.ai_packaging_proposal = external_proposal
        self.session.observation = observation
        self.observation = self.session.observation
        runtime_proposal = external_proposal or RecognitionService.proposal_from_shipment({})
        if is_first_visual_result:
            self._adopt_packaging(runtime_proposal)
        if conflicts:
            self._adopted_packaging().review_reasons.append("user confirmed facts conflict with image evidence")
        self._apply_observation(observation)
        self._refresh_display_summaries(observation, self._adopted_packaging())
        self.apply_proposal(self._adopted_packaging())
        if is_first_visual_result:
            self._maybe_capture_initial_ai_snapshot(observation, external_proposal)
            self._ai_baseline = {
                "summary": self._current_summary(),
                "product_summary": self.product_summary.text(),
                "packaging_summary": self.structure_summary.text(),
                "bare_spec": {
                    "length_cm": observation.length_cm, "width_cm": observation.width_cm,
                    "height_cm": observation.height_cm, "weight_g": observation.weight_g,
                },
                "normal_packaging": self._scenario_data(self.normal_fields),
            }
            self._accepted_bare_fields.clear()
            self._pending_confirmed_normal = {}
        self._recognized_image_fingerprint = self._image_fingerprint()
        self.ai_button.setText("AI识图")
        self.ai_button.setEnabled(False)
        if is_first_visual_result:
            self.packaging_stale = False
            self.manual_scenarios.clear()
        self._mark_dirty()
        self.recalculate()
        payload = observation.to_dict()
        missing = [key for key in ("product_cost_rmb", "domestic_shipping_rmb", "length_cm", "width_cm", "height_cm", "weight_g") if payload.get(key) in (None, "", "unknown")]
        op = self._diagnostic_operation
        adopted = self._adopted_packaging()
        if observation.raw_payload.get("vision_packaging_completion"):
            op.event("vision_packaging_estimate_missing", completion=observation.raw_payload["vision_packaging_completion"])
        salvage = adopted.candidate_records.get("candidate_field_salvage", {})
        if salvage:
            op.event("candidate_field_salvage", **dict(salvage.get("diagnostic") or {}),
                     final_source=adopted.proposal_source, adjustments=salvage.get("adjustments", []))
        op.event("ai_request_completed"); op.event("ai_response_parsed", returned_fields=[key for key,value in payload.items() if value not in (None,"","unknown")], missing_fields=missing); op.event("calibration_bypassed", reason="CAL77 runtime shipment arbitration disabled")
        generated=adopted.normal.is_complete() and adopted.conservative.is_complete()
        op.event("packaging_generated" if generated else "packaging_skipped", skip_reason=None if generated else "AI未返回完整发货尺寸/重量，等待人工填写")
        op.event("logistics_calculated" if self.current_quote else "logistics_skipped", reason=None if self.current_quote else "无可用包装尺寸和重量")
        op.event("page_updated", filled_fields=[key for key,value in {"product_summary":self.product_summary.text(),"structure_summary":self.structure_summary.text(),"bare_length":self.bare_length.value(),"bare_width":self.bare_width.value(),"bare_height":self.bare_height.value(),"bare_weight":self.bare_weight.value()}.items() if value not in (None,"",0)])
        op.event("operation_completed")
        op.summary(status="completed", returned_fields=[key for key,value in payload.items() if value not in (None,"","unknown")], missing_fields=missing, field_evidence=observation.raw_payload.get("field_evidence",{}), raw_observation=observation.raw_payload.get("observation", {}), normalized_codes={"product_type_code": observation.product_type_code, "product_family_code": observation.product_family_code, "material_family_code": observation.material_family_code}, value_types={"product_cost": observation.product_cost_value_type, "domestic_shipping": observation.domestic_shipping_value_type}, value_sources={"dimensions": observation.dimension_value_source, "weight": observation.weight_value_source}, ai_packaging_proposal=external_proposal.to_dict() if external_proposal else None, adopted_packaging=adopted.to_dict(), parse_error=None, matched_cal=[], cal_rejected_rules=[], cal_rejection_reasons=[], generic_fallback=False, packaging_generated=generated, normal_packaging=adopted.normal.to_dict() if generated else None, conservative_packaging=adopted.conservative.to_dict() if generated else None, not_generated_reason=[] if generated else ["AI未返回完整发货尺寸/重量，等待人工填写"], entered_logistics=self.current_quote is not None, logistics_skip_reason=None if self.current_quote else "无可用包装尺寸和重量", logistics_inputs=None, logistics_outputs=asdict(self.current_quote) if self.current_quote else None, page_filled_fields=[key for key,value in {"product_summary":self.product_summary.text(),"structure_summary":self.structure_summary.text(),"bare_length":self.bare_length.value(),"bare_width":self.bare_width.value(),"bare_height":self.bare_height.value(),"bare_weight":self.bare_weight.value()}.items() if value not in (None,"",0)], page_empty_fields=missing, warnings=adopted.review_reasons)

    @Slot(str, str)
    def _recognition_failed(self, category: str, message: str) -> None:
        if hasattr(self, "_diagnostic_operation"):
            self._diagnostic_operation.event("ai_response_parse_failed" if category == "response" else "ai_request_failed", category=category, message=message); self._diagnostic_operation.event("operation_completed", status="failed"); self._diagnostic_operation.summary(status="failed", returned_fields=[], missing_fields=[], field_evidence={}, parse_error=message, matched_cal=[], cal_rejected_rules=[], cal_rejection_reasons=[], packaging_generated=False, normal_packaging=None, conservative_packaging=None, not_generated_reason=[message], entered_logistics=False, logistics_skip_reason="AI请求失败", logistics_inputs=None, logistics_outputs=None, page_filled_fields=[], page_empty_fields=[], warnings=[])
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
        if self._ai_baseline is None or self._image_fingerprint() != self._recognized_image_fingerprint:
            self.ai_button.setEnabled(True)
        if thread is not None:
            thread.deleteLater()

    def collect_observation(self) -> AIObservation:
        observation = AIObservation.from_dict(self.observation.to_dict())
        observation.product_name = self.product_summary.text().strip()
        observation.display_product_summary = self.product_summary.text().strip()
        observation.display_packaging_summary = self.structure_summary.text().strip()
        # Product name is display text; keep the AI-normalized product_type for CAL routing.
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
        observation.product_cost_rmb = self.product_cost.value()
        observation.domestic_shipping_rmb = self.domestic_shipping.value()
        return observation

    # ------------------------------------------------------------------
    # 按修正重估
    # ------------------------------------------------------------------

    def reestimate_packaging(self) -> None:
        if self._local_thread is not None:
            return
        if self._ai_baseline is None:
            QMessageBox.information(self, "需要先识图", "请先完成一次 AI识图，再按用户修正重估。")
            return
        user_correction = self.user_correction.text().strip()
        if not user_correction:
            QMessageBox.information(self, "需要用户修正", "请先填写修正原因，再点击“按修正重估”。")
            return
        current = self.collect_observation()
        session_facts = self.session.confirmed_facts()
        confirmed_facts: dict[str, Any] = {}
        for field in ("length_cm", "width_cm", "height_cm", "weight_g"):
            if field in session_facts:
                confirmed_facts[field] = session_facts[field]["value"]
        context = {
            "product_name": self.product_summary.text().strip(),
            "confirmed_facts": confirmed_facts,
            "current_shipment": self._scenario_data(self.conservative_fields),
            "user_correction": user_correction,
        }
        self._local_diagnostic_operation = self.context.diagnostic_logger.begin_operation("local-reestimate")
        self._local_diagnostic_operation.event("corrected_reestimate_requested")
        reestimate_svc = self.context.local_reestimate_service
        bound = reestimate_svc.profile_store.bound_profile(LOCAL_REESTIMATE) if reestimate_svc.profile_store else None
        provider_info: dict[str, Any] = {}
        if bound is not None:
            _profile, _ = bound
            from urllib.parse import urlparse as _urlparse
            provider_info = {
                "provider": _profile.provider,
                "model": _profile.model_name,
                "provider_host": _urlparse(_profile.api_url).netloc,
            }
        self._local_diagnostic_operation.request(request_type="corrected-reestimate-v1", **provider_info, **context)
        self._show_local_dialog()
        self._local_thread = QThread(self)
        self._local_worker = LocalReestimateWorker(self.context.local_reestimate_service, context)
        self._local_worker.moveToThread(self._local_thread)
        self._local_thread.started.connect(self._local_worker.run)
        self._local_worker.completed.connect(self._local_reestimate_completed)
        self._local_worker.failed.connect(self._local_reestimate_failed)
        self._local_worker.completed.connect(self._local_thread.quit)
        self._local_worker.failed.connect(self._local_thread.quit)
        self._local_thread.finished.connect(self._local_thread_finished)
        self._local_thread.finished.connect(self._local_worker.deleteLater)
        self._local_thread.start()

    def _scenario_data(self, fields: dict[str, Any]) -> dict[str, Any]:
        proposal = self._adopted_packaging()
        scenario = proposal.normal if proposal and fields is self.normal_fields else (proposal.conservative if proposal else None)
        return {
            "packaging_method": fields.get("method").text().strip() if fields.get("method") else (scenario.packaging_method if scenario else ""),
            "length_cm": fields["length"].value() or None,
            "width_cm": fields["width"].value() or None,
            "height_cm": fields["height"].value() or None,
            "weight_g": fields["weight"].value() or None,
        }

    def _current_summary(self) -> str:
        return "；".join(value for value in (self.product_summary.text().strip(), self.structure_summary.text().strip()) if value)

    def _show_local_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("按修正重估")
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setFixedSize(300, 92)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 14)
        label = QLabel("正在按修正重新估算，请稍候")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("sectionTitle", True)
        layout.addWidget(label)
        self._local_dialog = dialog
        dialog.show()

    @Slot(object)
    def _local_reestimate_completed(self, result: Any) -> None:
        if self._local_dialog is not None:
            self._local_dialog.close()
        proposal = result.packaging_proposal
        scenario = result.shipment or (proposal.normal if proposal else None)
        if proposal is None or scenario is None or not scenario.is_complete():
            QMessageBox.warning(self, "按修正重估失败", "模型未返回完整有效的发货尺寸和重量，当前采用未改变。")
            return
        message = (
            "重新估算结果\n\n"
            f"{scenario.length_cm:g} × {scenario.width_cm:g} × {scenario.height_cm:g} cm\n"
            f"{scenario.weight_g:g} g\n"
            f"{scenario.packaging_method or '发货状态待确认'}"
        )
        accepted = confirm_action(
            self,
            "重新估算结果",
            message,
            confirm_text="采用此结果",
        )
        op = getattr(self, "_local_diagnostic_operation", None)
        provider_meta = {"provider": result.provider, "model": result.model, "provider_host": result.provider_host}
        if not accepted:
            if op:
                op.event("corrected_reestimate_cancelled", elapsed_ms=result.elapsed_ms)
                op.response(provider_raw_response=None, normalized_result={"shipment": scenario.to_dict()}, parse_error=None, elapsed_ms=result.elapsed_ms, **provider_meta)
                op.summary(status="cancelled", returned_fields=["shipment"], missing_fields=[], field_evidence={}, parse_error=None, matched_cal=[], cal_rejected_rules=[], cal_rejection_reasons=[], packaging_generated=True, normal_packaging=scenario.to_dict(), conservative_packaging=None, not_generated_reason=[], entered_logistics=False, logistics_skip_reason="候选已取消，当前采用未改变", logistics_inputs=None, logistics_outputs=None, page_filled_fields=[], page_empty_fields=[], warnings=[])
            return

        baseline = self._adopted_packaging()
        if baseline is None:
            return
        adopted_current = replace(scenario, label="当前采用")
        self._adopt_packaging(replace(baseline, conservative=adopted_current))
        previous_updating = self._updating
        self._updating = True
        try:
            self.conservative_fields["method"].setText(scenario.packaging_method)
            for key, field in (("length_cm", self.conservative_fields["length"]),
                               ("width_cm", self.conservative_fields["width"]),
                               ("height_cm", self.conservative_fields["height"]),
                               ("weight_g", self.conservative_fields["weight"])):
                field.setValue(float(getattr(scenario, key) or 0))
        finally:
            self._updating = previous_updating
        self.manual_scenarios.add("当前采用")
        self.user_calibration_dirty = True
        self.packaging_stale = False
        self.review_badge.setText("已采用修正重估 · 需要复核")
        self.review_badge.setProperty("warning", True)
        self.review_badge.setProperty("success", False)
        self._refresh_badge_style()
        self._mark_dirty()
        self.recalculate()
        if op:
            op.event("corrected_reestimate_adopted", elapsed_ms=result.elapsed_ms)
            op.event("calibration_bypassed", reason="CAL77 runtime shipment arbitration disabled")
            op.event("operation_completed")
            op.response(provider_raw_response=None, normalized_result={"shipment": scenario.to_dict()}, parse_error=None, elapsed_ms=result.elapsed_ms, **provider_meta)
            op.summary(status="completed", returned_fields=["shipment"], missing_fields=[], field_evidence={}, parse_error=None, matched_cal=[], cal_rejected_rules=[], cal_rejection_reasons=[], packaging_generated=True, normal_packaging=scenario.to_dict(), conservative_packaging=scenario.to_dict(), not_generated_reason=[], entered_logistics=self.current_quote is not None, logistics_skip_reason=None if self.current_quote else "没有可用包装尺寸和重量", logistics_inputs=None, logistics_outputs=asdict(self.current_quote) if self.current_quote else None, page_filled_fields=["length_cm", "width_cm", "height_cm", "weight_g", "state"], page_empty_fields=[], warnings=[], **provider_meta)

    @Slot(str, str)
    def _local_reestimate_failed(self, category: str, message: str) -> None:
        if hasattr(self, "_local_diagnostic_operation"):
            self._local_diagnostic_operation.event("local_reestimate_failed", category=category, message=message)
            self._local_diagnostic_operation.event("operation_completed", status="failed")
            self._local_diagnostic_operation.response(provider_raw_response=None, normalized_result=None, parse_error=message)
            self._local_diagnostic_operation.summary(status="failed", returned_fields=[], missing_fields=[], field_evidence={}, parse_error=message, matched_cal=[], cal_rejected_rules=[], cal_rejection_reasons=[], packaging_generated=False, normal_packaging=None, conservative_packaging=None, not_generated_reason=[message], entered_logistics=False, logistics_skip_reason="按修正重估失败", logistics_inputs=None, logistics_outputs=None, page_filled_fields=[], page_empty_fields=[], warnings=[])
        title = "按修正重估不可用" if category == "unavailable" else "按修正重估失败"
        QMessageBox.warning(self, title, message)

    def _local_thread_finished(self) -> None:
        if self._local_dialog is not None:
            self._local_dialog.close()
            self._local_dialog.deleteLater()
        thread = self._local_thread
        self._local_dialog = None
        self._local_worker = None
        self._local_thread = None
        if thread is not None:
            thread.deleteLater()

    # ------------------------------------------------------------------
    # 包装应用与选择
    # ------------------------------------------------------------------

    def apply_proposal(self, proposal: PackagingProposal) -> None:
        previous_updating = self._updating
        self._updating = True
        # 只在第一次 AI（initial_ai_snapshot 尚未捕获）时写入两框：
        # AI估算与当前采用复制完全相同的首次 AI 数据；
        # 同会话再次 AI / 按修正重估不得静默覆盖已冻结的首次结果或用户已编辑的当前采用；
        # 历史编辑模式下（含无 ai_initial 的旧记录）同样不得覆盖已恢复的两卡。
        if self.initial_ai_snapshot is None and self.editing_record_id is None:
            for fields in (self.normal_fields, self.conservative_fields):
                method_text = proposal.normal.packaging_method
                fields["method"].setText(
                    packaging_method_zh(method_text) if fields is self.normal_fields else method_text
                )
                fields["length"].setValue(proposal.normal.length_cm or 0)
                fields["width"].setValue(proposal.normal.width_cm or 0)
                fields["height"].setValue(proposal.normal.height_cm or 0)
                fields["weight"].setValue(proposal.normal.weight_g or 0)
        self._updating = previous_updating
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
        # 历史编辑模式：恢复后的记录允许直接修改任何字段并重算保存，
        # 不得因裸规格/摘要变化把包装标记为过期而阻止保存。
        if self.proposal is not None and self.editing_record_id is None:
            self.packaging_stale = True
            self.review_badge.setText("估算已过期 · 禁止保存")
            self.review_badge.setProperty("warning", True)
            self.review_badge.setProperty("success", False)
            self._refresh_badge_style()
        self.recalculate()

    def _user_calibration_changed(self) -> None:
        """当前采用尺寸/重量或用户修正被用户手动修改 → 用户校准 dirty。"""
        self.user_calibration_dirty = True
        self._mark_dirty()

    def _scenario_manually_changed(self, name: str) -> None:
        if self._updating:
            return
        self.manual_scenarios.add(name)
        # 当前采用是用户校准入口 A：手动修改计入用户校准 dirty；
        # AI 首次自动复制走程序化 setValue，不会进入这里。
        if name == "当前采用":
            self.user_calibration_dirty = True
        self.review_badge.setText("人工修改 · 需要复核")
        self.review_badge.setProperty("warning", True)
        self.review_badge.setProperty("success", False)
        self._refresh_badge_style()
        self._mark_dirty()
        self.recalculate()

    def _select_package(self, name: str, *, user: bool) -> None:
        """旧选档入口（兼容调用）：当前采用是唯一正式输入，不再存在选档操作。"""
        del name, user
        self._style_card(self.normal_fields, selected=False)
        self._style_card(self.conservative_fields, selected=True)
        self.recalculate()

    @staticmethod
    def _style_card(fields: dict[str, Any], *, selected: bool) -> None:
        card = fields.get("card")
        if card is None:
            return
        card.setProperty("choiceSelected", selected)
        card.setProperty("choiceFrozen", not selected)
        card.style().unpolish(card)
        card.style().polish(card)
        card.update()

    def current_scenario(self) -> PackagingScenario:
        """当前采用（右卡）是唯一正式包装计算输入；AI估算只作对照，不参与计算。"""
        fields = self.conservative_fields
        label = str(fields["name"])
        source = self._adopted_packaging().conservative if self._adopted_packaging() else None
        manual = label in self.manual_scenarios
        method_text = fields["method"].text().strip() if fields.get("method") else ""
        return PackagingScenario(
            label=label,
            packaging_state=source.packaging_state if source else self.observation_to_state(),
            packaging_method=method_text or (source.packaging_method if source else ""),
            length_cm=fields["length"].value() or None,
            width_cm=fields["width"].value() or None,
            height_cm=fields["height"].value() or None,
            weight_g=fields["weight"].value() or None,
            reasoning_summary=method_text or (source.reasoning_summary if source else ""),
            confidence="low" if manual else (source.confidence if source else "low"),
            needs_review=True if manual else (source.needs_review if source else True),
            default_fields_used=list(source.default_fields_used) if source else [],
        )

    def observation_to_state(self):
        from profit_accounting_26.domain.models import PackagingState
        return PackagingState.UNKNOWN

    # ------------------------------------------------------------------
    # 货代与成本
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 尾程 USD → RMB 实时联动（直连 valueChanged；遵守 _loading_record）
    # ------------------------------------------------------------------

    def _tail_usd_live_changed(self, _value: float) -> None:
        """主页尾程 USD 实时变化：读取当前有效汇率 → 更新冻结 RMB → 立即全链路重算。

        不等待用户点击保存汇率；不要求再次点击系统计算；不修改 settings.json；
        修改当前 CalculationPage 的实时状态。
        记录加载 / 快照保护期间（_loading_record）不触发实时重算。
        """
        if self._updating:
            return
        if getattr(self.profit_binder, '_loading_record', False):
            return
        self._sync_tail_rmb_from_usd(recalculate=True)

    def _sync_tail_rmb_from_usd(self, *, recalculate: bool) -> None:
        """USD → RMB 单向同步：RMB = USD × 当前有效汇率，使用 QSignalBlocker 更新冻结 RMB。

        用于：
        - 页面初始化（recalculate=False）
        - 尾程 USD 编辑器实时联动（recalculate=True）
        - refresh_settings / 汇率变化后同步（通常结合立即 recalculate）
        """
        rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        if rate <= 0:
            rate = 7.2
        usd = self.tail_fee_usd.value()
        rmb = round(usd * rate, 2)
        # 使用 QSignalBlocker 更新冻结 RMB，避免信号递归
        with QSignalBlocker(self.tail_fee_rmb.spin):
            self.tail_fee_rmb.spin.setValue(rmb)
        if recalculate:
            self.recalculate()

    def _clear_calculation(self, message: str) -> None:
        self.current_quote = None
        self.current_forwarder = None
        self.current_system_cost = None
        for card in self.quote_cards.values():
            card.update_quote(None)
        for value in self.system_rows.values():
            if value is not None:
                value.setText("—")
                self._set_zero_warn(value, False)
        if self.system_total is not None:
            self.system_total.setText("—")
        if self.system_total_usd is not None:
            self.system_total_usd.setText("—")
        first_mile_name = self.system_names.get("first_mile")
        if first_mile_name is not None:
            first_mile_name.setText("头程（—）")
        self.profit_binder.set_calculation_cost(0.0)
        del message  # 提示文案由利润区与复核徽标承载

    def recalculate(self) -> None:
        if self._updating:
            return
        if self.packaging_stale:
            self._clear_calculation("包装估算已过期，请重新估算后再计算和保存。")
            return
        scenario = self.current_scenario()
        forwarders = self.context.settings_service.forwarders_from_settings(self.settings)
        enabled = [item for item in forwarders if item.enabled and not item.archived]
        # 0 是合法金额：商品成本/国内运费为 0 不阻止物流与总成本计算
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
        product_cost = self.product_cost.value()
        domestic_shipping = self.domestic_shipping.value()
        system_cost = product_cost + domestic_shipping + selected_quote.total_logistics_rmb
        self.current_system_cost = system_cost
        # 六行只读当前正式 Calculation 结果，不在 UI 重新实现成本公式；
        # 采购成本/国内运费为 0 时仅用红色弱提醒，不阻止计算。
        self._set_system_row("product", f"¥{product_cost:.2f}", zero_warn=product_cost == 0)
        self._set_system_row("domestic", f"¥{domestic_shipping:.2f}", zero_warn=domestic_shipping == 0)
        short_name = str(selected_forwarder.name or "").rstrip("货代") or str(selected_forwarder.name or "")
        first_mile_name = self.system_names.get("first_mile")
        if first_mile_name is not None:
            first_mile_name.setText(f"头程（{short_name}）")
        self._set_system_row("first_mile", f"¥{selected_quote.weight_fee_rmb:.2f}")
        self._set_system_row("service", f"¥{selected_quote.fixed_fee_rmb:.2f}")
        self._set_system_row("tail", f"¥{self.tail_fee_rmb.value():.2f}")
        rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        if self.system_total is not None:
            self.system_total.setText(f"¥{system_cost:.2f}")
        if self.system_total_usd is not None:
            self.system_total_usd.setText(f"${system_cost / rate:.2f}" if rate > 0 else "—")
        self.profit_binder.set_calculation_cost(system_cost)
        self.context.diagnostic_logger.event("forwarder_calculated", package=scenario.to_dict(), forwarder_id=selected_forwarder.id, quote=asdict(selected_quote), system_cost=system_cost)

    def _set_system_row(self, key: str, text: str, *, zero_warn: bool = False) -> None:
        label = self.system_rows.get(key)
        if label is not None:
            label.setText(text)
            self._set_zero_warn(label, zero_warn)

    @staticmethod
    def _set_zero_warn(label: QLabel, enabled: bool) -> None:
        """0 金额红色弱提醒：只改动态属性，不弹错、不改值、不阻止计算。"""
        if label.property("zeroWarn") == enabled:
            return
        label.setProperty("zeroWarn", enabled)
        label.style().unpolish(label)
        label.style().polish(label)

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def build_record_payload(self) -> dict[str, Any]:
        scenario = self.current_scenario()
        normal = PackagingScenario(
            label="正常档",
            packaging_state=self._adopted_packaging().normal.packaging_state if self._adopted_packaging() else scenario.packaging_state,
            packaging_method=self._adopted_packaging().normal.packaging_method if self._adopted_packaging() else "",
            length_cm=self.normal_fields["length"].value() or None,
            width_cm=self.normal_fields["width"].value() or None,
            height_cm=self.normal_fields["height"].value() or None,
            weight_g=self.normal_fields["weight"].value() or None,
            reasoning_summary=self._adopted_packaging().normal.reasoning_summary if self._adopted_packaging() else "",
            # AI估算（左卡）只读，永远不会被人工修改
            confidence="medium",
            needs_review=False,
        )
        conservative = PackagingScenario(
            label="保守档",
            packaging_state=self._adopted_packaging().conservative.packaging_state if self._adopted_packaging() else scenario.packaging_state,
            packaging_method=self.conservative_fields["method"].text(),
            length_cm=self.conservative_fields["length"].value() or None,
            width_cm=self.conservative_fields["width"].value() or None,
            height_cm=self.conservative_fields["height"].value() or None,
            weight_g=self.conservative_fields["weight"].value() or None,
            reasoning_summary=self._adopted_packaging().conservative.reasoning_summary if self._adopted_packaging() else "",
            # 当前采用（右卡）是唯一正式输入；用户修改即需要复核
            confidence="low" if ("当前采用" in self.manual_scenarios or "保守档" in self.manual_scenarios) else "medium",
            needs_review="当前采用" in self.manual_scenarios or "保守档" in self.manual_scenarios,
        )
        profit_scenarios = self.profit_binder.export_profit_scenarios()
        no_activity = profit_scenarios.get("no_activity", {})
        activity = profit_scenarios.get("activity", {})
        # 快照/旧记录兼容状态下，layers 中的汇率/成本/利润必须来自
        # profit_scenarios 快照，不得混入当前 settings 或 current_system_cost。
        # 成本只要字段存在就原样使用（包括合法的 0），只有字段不存在/None 才回退。
        if self.profit_binder.is_in_snapshot_mode():
            ps_rate = profit_scenarios.get("exchange_rate")
            exchange_rate = float(ps_rate) if ps_rate is not None else float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
            ps_cost = profit_scenarios.get("calculation_total_cost_rmb")
            system_cost_for_record = float(ps_cost) if ps_cost is not None else (self.current_system_cost or 0.0)
            adopted_cost = float(ps_cost) if ps_cost is not None else self.profit_binder._calculation_total_cost_rmb
        else:
            exchange_rate = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
            system_cost_for_record = self.current_system_cost
            adopted_cost = self.profit_binder._calculation_total_cost_rmb
        return {
            "product_name": self.product_summary.text().strip(),
            "product_link": self.product_link.text().strip() if self.product_link else "",
            "status": "active",
            "layers": {
                "ai_raw": {
                    "observation": self.collect_observation().to_dict(),
                    "packaging_proposal": (
                        self.session.ai_packaging_proposal.to_dict()
                        if self.session.ai_packaging_proposal else (
                            self._adopted_packaging().to_dict() if self._adopted_packaging() else {}
                        )
                    ),
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
                    # 当前采用是唯一正式输入；固定指向 conservative 槽，
                    # 使 record_service 派生的 current_estimate 始终等于当前采用。
                    "selected_packaging": "保守档",
                    "selected_forwarder_id": self.selected_forwarder_id,
                    "calculation_cost_rmb": adopted_cost,
                    "packaging_estimate_stale": self.packaging_stale,
                },
                "calculated": {
                    "system_cost_rmb": system_cost_for_record,
                    "sale_price_usd": no_activity.get("sale_price_usd", 0.0),
                    "reserve_percent": profit_scenarios.get("reserve_percent", 0.0),
                    "profit_rmb": no_activity.get("profit_rmb", 0.0),
                    "profit_rate_percent": (activity.get("profit_rate_on_cost") or 0.0) * 100.0,
                    "exchange_rate": exchange_rate,
                    "tail_fee_rmb": self.tail_fee_rmb.value(),
                    "selected_profit_rule_id": self.profit_binder.selected_rule_id,
                    "total_logistics_rmb": self.current_quote.total_logistics_rmb if self.current_quote else None,
                    "logistics_quote": asdict(self.current_quote) if self.current_quote else {},
                    "forwarder_name": self.current_forwarder.name if self.current_forwarder else "",
                    "logistics_engine_version": "deterministic-logistics-v1",
                    "packaging_engine_version": (
                        self._adopted_packaging().engine_version
                        if self._adopted_packaging() else "vision-runtime-v1"
                    ),
                    "calibration_version": (
                        self._adopted_packaging().calibration_version
                        if self._adopted_packaging() else ""
                    ),
                    "schema_version": "2.6.1",
                },
                "actual": {},
            },
            "product_cost_rmb": self.product_cost.value(),
            "domestic_shipping_rmb": self.domestic_shipping.value(),
            "shein_quote_usd": profit_scenarios.get("shein_quote_usd", 0.0),
            "profit_scenarios": profit_scenarios,
        }

    def save_record(self) -> None:
        is_update = self.record_id is not None
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
                self.build_record_payload(),
                images=images.images,
                record_id=self.record_id,
                ai_initial=(self.initial_ai_snapshot if self.record_id is None else None),
            )
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        try:
            self._save_user_feedback()
        except Exception as exc:
            self.context.diagnostic_logger.event("user_feedback_save_failed", record_id=self.record_id, error=str(exc))
            QMessageBox.warning(self, "用户修正未保存", f"记录已保存，但用户修正保存失败：{exc}")
        self.mark_saved()
        self.context.diagnostic_logger.event("record_saved", record_id=self.record_id)
        # The local reestimate baseline belongs to one unsaved measurement
        # session only.  Saving ends that session; the record itself keeps its
        # existing auditable AI/adopted layers.
        self._ai_baseline = None
        self._recognized_image_fingerprint = ()
        self.ai_button.setText("AI识图")
        self.ai_button.setEnabled(True)
        self.saved.emit(self.record_id)
        if is_update:
            QMessageBox.information(self, "更新成功", f"历史记录已更新：{self.record_id}")
        else:
            QMessageBox.information(self, "保存成功", f"记录已保存：{self.record_id}")

    def _save_user_feedback(self) -> None:
        """把用户校准（当前采用 + 用户修正）保存为 CalibrationFeedback（source=user）。

        主界面的当前采用属于用户校准入口 A，不是实际发货实测：
        suggested_package 恒为 user_suggested，绝不写 actual_logistics，
        也绝不标记 actual_measured。
        仅当用户校准 dirty（手动改当前采用或填写用户修正）时才写建议值；
        AI 首次自动复制不产生校准反馈。
        已有 feedback 时更新同一个 feedback_id，并保留其中已录入的
        建议值、实测数据与结构反馈，不重复创建。
        """
        if not self.record_id:
            return
        note = self.user_correction.text().strip() or None
        adopted = self._card_package_dict(self.conservative_fields)
        keys = ("packaging_method", "length_cm", "width_cm", "height_cm", "weight_g")
        adopted_filled = any(adopted[key] is not None for key in keys)
        suggested = None
        if self.user_calibration_dirty and adopted_filled:
            suggested = dict(adopted)
            suggested["evidence_level"] = "user_suggested"
        actual = self._actual_first_mile_dict()
        if note is None and suggested is None and not actual:
            return
        data: dict[str, Any] = {"record_id": self.record_id, "source": "user", "user_note": note}
        if suggested is not None:
            data["suggested_package"] = suggested
        if actual:
            data["actual_logistics"] = dict(actual)
        if self.current_feedback_id:
            try:
                existing = self.context.calibration_feedback_service.load(self.current_feedback_id)
            except KeyError:
                self.current_feedback_id = None
            else:
                # 更新时保留对话框已录入的建议值、实际测量与结构反馈，禁止互相清掉
                data["feedback_id"] = existing.feedback_id
                if suggested is None and existing.suggested_package is not None and existing.suggested_package.has_content():
                    data["suggested_package"] = existing.suggested_package.to_dict()
                if actual:
                    existing_actual = (
                        existing.actual_logistics.to_dict()
                        if existing.actual_logistics is not None and existing.actual_logistics.has_content()
                        else {}
                    )
                    data["actual_logistics"] = {**existing_actual, **actual}
                elif existing.actual_logistics is not None and existing.actual_logistics.has_content():
                    data["actual_logistics"] = existing.actual_logistics.to_dict()
                if existing.structure.has_content():
                    data["structure"] = existing.structure.to_dict()
        feedback_id = self.context.calibration_feedback_service.save(data)
        if feedback_id != self.current_feedback_id:
            self.current_feedback_id = feedback_id
            self.context.history_record_v2_service.link_feedback(self.record_id, feedback_id)
        # 用户校准入口 A 同步 current_estimate：与历史页“编辑校准”入口 B 更新同一条
        if suggested is not None:
            self.context.history_record_v2_service.update_current_estimate(self.record_id, dict(suggested))

    @staticmethod
    def _card_package_dict(fields: dict[str, Any]) -> dict[str, Any]:
        """读取一个包装卡片为五字段 dict（空值归一为 None）。"""
        method_text = str(fields["method"].text()).strip() if fields.get("method") else ""
        return {
            "packaging_method": method_text or None,
            "length_cm": fields["length"].value() or None,
            "width_cm": fields["width"].value() or None,
            "height_cm": fields["height"].value() or None,
            "weight_g": fields["weight"].value() or None,
        }

    # ------------------------------------------------------------ 真实头程

    def _build_actual_first_mile_row(self, grid: QGridLayout, row: int) -> None:
        """当前采用卡最底部的真实头程：只记录，不参与任何当前计算。"""
        row_widget = QWidget()
        row_widget.setObjectName("actualFirstMileRow")
        self.actual_first_mile_row = row_widget
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        label = QLabel("真实头程")
        label.setObjectName("actualFirstMileLabel")
        row_layout.addWidget(label)
        self.actual_forwarder_combo = QComboBox()
        self.actual_forwarder_combo.setObjectName("actualFirstMileForwarder")
        self.actual_forwarder_combo.setFixedWidth(88)
        self.actual_forwarder_combo.setFixedHeight(28)
        self.actual_forwarder_combo.setStyleSheet("QComboBox { min-height: 0px; max-height: 28px; }")
        self._reload_actual_forwarder_combo()
        row_layout.addWidget(self.actual_forwarder_combo)
        symbol = QLabel("¥")
        symbol.setObjectName("actualFirstMileCurrency")
        symbol.setProperty("muted", True)
        row_layout.addWidget(symbol)
        self.actual_first_mile_fee_edit = QLineEdit()
        self.actual_first_mile_fee_edit.setObjectName("actualFirstMileFee")
        self.actual_first_mile_fee_edit.setPlaceholderText("0.00")
        self.actual_first_mile_fee_edit.setFixedWidth(58)
        self.actual_first_mile_fee_edit.setFixedHeight(28)
        self.actual_first_mile_fee_edit.setStyleSheet("QLineEdit { min-height: 0px; max-height: 28px; }")
        validator = QDoubleValidator(0.0, 1_000_000.0, 2, self.actual_first_mile_fee_edit)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.actual_first_mile_fee_edit.setValidator(validator)
        row_layout.addWidget(self.actual_first_mile_fee_edit)
        row_layout.addStretch(1)
        hint = QLabel("选填，仅记录，不影响计算")
        hint.setObjectName("actualFirstMileHint")
        hint.setProperty("muted", True)
        hint_font = hint.font()
        if hint_font.pointSize() > 8:
            hint_font.setPointSize(hint_font.pointSize() - 1)
        hint.setFont(hint_font)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        column.addWidget(row_widget)
        column.addWidget(hint)
        grid.addLayout(column, row, 0, 1, 3)

    def _reload_actual_forwarder_combo(self, *, keep: str | None = None) -> None:
        """货代下拉只显示未归档货代；keep 为已归档旧货代名时也加入（不丢历史事实）。"""
        combo = getattr(self, "actual_forwarder_combo", None)
        if combo is None:
            return
        current = keep if keep is not None else combo.currentText()
        forwarders = self.context.settings_service.forwarders_from_settings(self.settings)
        names = [item.name for item in forwarders if not item.archived]
        if current and current not in names:
            names = [current] + names
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItems(names)
            if current:
                index = combo.findText(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
        finally:
            combo.blockSignals(False)

    def _actual_first_mile_dict(self) -> dict[str, Any]:
        """读取真实头程输入：留空返回空 dict（不写 actual_logistics）；0 是合法值。"""
        text = self.actual_first_mile_fee_edit.text().strip()
        if not text:
            return {}
        try:
            fee = float(text)
        except ValueError:
            return {}
        forwarder = self.actual_forwarder_combo.currentText().strip() or None
        return {"actual_first_mile_fee_rmb": fee, "actual_forwarder": forwarder}

    def _prefill_actual_first_mile(self, fee: float | None, forwarder: str | None) -> None:
        """打开历史记录时预填已保存的真实头程（含已归档货代名）。"""
        if not hasattr(self, "actual_first_mile_fee_edit"):
            return
        if forwarder:
            self._reload_actual_forwarder_combo(keep=forwarder)
        if fee is not None:
            self.actual_first_mile_fee_edit.setText(f"{fee:g}")

    def clear_new(self) -> None:
        if self.dirty:
            if not confirm_action(
                self,
                "清空并新建",
                "当前存在未保存修改，确定清空并新建吗？",
            ):
                return
        self._updating = True
        self.record_id = None
        self.editing_record_id = None
        self.user_calibration_dirty = False
        self.observation = AIObservation()
        self.proposal = None
        self.session = CalculationSession()
        self._ai_baseline = None
        self.initial_ai_snapshot = None
        self.current_feedback_id = None
        self.user_correction.clear()
        if hasattr(self, "actual_first_mile_fee_edit"):
            self.actual_first_mile_fee_edit.clear()
            self._reload_actual_forwarder_combo()
        self._recognized_image_fingerprint = ()
        self._accepted_bare_fields.clear()
        self._pending_confirmed_normal = {}
        self.packaging_stale = False
        self.manual_scenarios.clear()
        self.product_summary.clear()
        self.material_summary.clear()
        self.structure_summary.clear()
        if self.product_link is not None:
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
        ):
            widget.setValue(0)
        for fields in (self.normal_fields, self.conservative_fields):
            fields["method"].setText("")
            for key in ("length", "width", "height", "weight"):
                fields[key].setValue(0)
        for slot in self.image_slots:
            slot.clear_image()
        self._updating = False
        self.package_selection_changed = False
        self.forwarder_selection_changed = False
        self._select_package("正常档", user=False)
        self.profit_binder.reset()
        self.review_badge.setText("待识别")
        self.review_badge.setProperty("warning", True)
        self._refresh_badge_style()
        self._refresh_edit_mode_ui()
        self.mark_saved()
        self.recalculate()

    def load_record_payload(self, record_id: str) -> None:
        self.context.diagnostic_logger.event("record_restore_requested", record_id=record_id)
        try:
            record = self.context.record_service.load(record_id)
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            return
        self._updating = True
        self.manual_scenarios.clear()
        self.record_id = record_id
        # 进入历史编辑模式：恢复后修改任何字段都允许直接重算并更新同一条记录
        self.editing_record_id = record_id
        self.user_calibration_dirty = False
        # 每条历史记录独立恢复真实头程；先清掉前一条记录残留的金额和货代，
        # 仅当前记录实际保存了该字段时才在后面预填。
        self.actual_first_mile_fee_edit.clear()
        self._reload_actual_forwarder_combo(keep=None)
        self.product_summary.setText(str(record.get("product_name") or ""))
        if self.product_link is not None:
            self.product_link.setText(str(record.get("product_link") or ""))
        self.product_cost.setValue(float(record.get("product_cost_rmb", 0)))
        self.domestic_shipping.setValue(float(record.get("domestic_shipping_rmb", 0)))
        layers = record.get("layers", {})
        ai_raw = layers.get("ai_raw", {})
        observation_raw = ai_raw.get("observation") or {}
        if observation_raw:
            self.observation = AIObservation.from_dict(observation_raw)
            self._apply_observation(self.observation)
        proposal_raw = ai_raw.get("packaging_proposal") or {}
        if proposal_raw:
            try:
                self._adopt_packaging(PackagingProposal.from_dict(proposal_raw))
            except Exception:
                self.proposal = None
                self.session.adopted_packaging = None
        adopted = layers.get("adopted", {})
        # 恢复历史记录后不再携带过期阻断：保存按钮随时可更新同一条记录
        self.packaging_stale = False
        bare = adopted.get("bare", {})
        self.bare_length.setValue(float(bare.get("length_cm") or 0))
        self.bare_width.setValue(float(bare.get("width_cm") or 0))
        self.bare_height.setValue(float(bare.get("height_cm") or 0))
        self.bare_weight.setValue(float(bare.get("weight_g") or 0))
        # AI估算（左卡）：优先第一次 AI 结果（_v2.ai_initial），旧记录回退 adopted.normal
        v2 = record.get("_v2") if isinstance(record.get("_v2"), dict) else {}
        ai_initial = v2.get("ai_initial") if isinstance(v2.get("ai_initial"), dict) else {}
        # 恢复第一次 AI 冻结门控：后续再次 AI 识图不得覆盖 AI估算/当前采用两卡；
        # 旧记录没有 ai_initial 时同样冻结（用空快照占位），历史更新由 V2Service 保留 ai_initial
        self.initial_ai_snapshot = dict(ai_initial) if ai_initial else {}
        ai_initial_pkg = ai_initial.get("adopted_packaging") if isinstance(ai_initial.get("adopted_packaging"), dict) else {}
        left_raw = ai_initial_pkg.get("normal") if isinstance(ai_initial_pkg.get("normal"), dict) else None
        self._fill_package_fields(self.normal_fields, left_raw or adopted.get("normal", {}))
        # 当前采用（右卡）：优先 current_estimate，旧记录回退 selected 槽（不伪造第一次 AI 数据）
        current_estimate = v2.get("current_estimate")
        right_raw = None
        if isinstance(current_estimate, dict) and any(current_estimate.get(key) is not None for key in ("packaging_method", "length_cm", "width_cm", "height_cm", "weight_g")):
            right_raw = current_estimate
        else:
            selected_slot = str(adopted.get("selected_packaging") or "正常档")
            right_raw = adopted.get("conservative" if selected_slot == "保守档" else "normal", {})
        self._fill_package_fields(self.conservative_fields, right_raw)
        if adopted.get("conservative", {}).get("needs_review"):
            self.manual_scenarios.add("当前采用")
        if adopted.get("normal", {}).get("needs_review") and not self.observation.display_packaging_summary:
            legacy_instruction = str(adopted.get("normal", {}).get("packaging_method") or "").strip()
            if legacy_instruction:
                self.observation.display_packaging_summary = legacy_instruction
                self.structure_summary.setText(legacy_instruction)
        # 用户修正与 feedback 关联恢复（同一 feedback_id 更新语义）
        self.current_feedback_id = str(v2.get("calibration_feedback_id") or "") or None
        self.user_correction.clear()
        if self.current_feedback_id:
            try:
                feedback = self.context.calibration_feedback_service.load(self.current_feedback_id)
            except KeyError:
                self.current_feedback_id = None
            else:
                if feedback.user_note:
                    self.user_correction.setText(feedback.user_note)
                if feedback.actual_logistics is not None and feedback.actual_logistics.has_content():
                    self._prefill_actual_first_mile(
                        feedback.actual_logistics.actual_first_mile_fee_rmb,
                        feedback.actual_logistics.actual_forwarder,
                    )
        # 程序化恢复不算用户修改：复位用户校准 dirty
        self.user_calibration_dirty = False
        selected_package = str(adopted.get("selected_packaging") or "正常档")
        self.selected_forwarder_id = str(adopted.get("selected_forwarder_id") or self.selected_forwarder_id)
        calculated = layers.get("calculated", {})
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
        # 打开记录前捕获当前设置（汇率/启用规则/选中规则），
        # 供退出快照显示模式时恢复为当前推算依据。
        # 直接读 settings_service 最新值，避免页面缓存过期。
        current_settings = self.context.settings_service.load()
        self.profit_binder.capture_current_settings(
            exchange_rate=float(current_settings.get("exchange_rate_usd_to_rmb", 7.2)),
            rules=tuple(
                rule for rule in self.context.settings_service.rules_from_settings(current_settings)
                if rule.enabled and not rule.archived
            ),
            selected_rule_id=str(current_settings.get("selected_profit_rule_id") or ""),
        )
        self.profit_binder.set_selected_rule_id(self.selected_profit_rule_id)
        # 记录加载保护：内部 _select_package/recalculate/set_calculation_cost
        # 期间不得退出历史快照；恢复结束后在 finally 中复位。
        self.profit_binder._loading_record = True
        try:
            self.profit_binder.load_from_record(record)
            self._select_package(selected_package, user=False)
            if self.packaging_stale:
                self.review_badge.setText("估算已过期 · 禁止保存")
                self.review_badge.setProperty("warning", True)
                self.review_badge.setProperty("success", False)
            elif self.proposal is not None:
                if self.proposal.needs_review or self.manual_scenarios:
                    self.review_badge.setText("需要复核")
                    self.review_badge.setProperty("warning", True)
                    self.review_badge.setProperty("success", False)
                else:
                    self.review_badge.setText("已载入")
                    self.review_badge.setProperty("success", True)
                    self.review_badge.setProperty("warning", False)
            else:
                self.review_badge.setText("人工方案 · 需要复核")
                self.review_badge.setProperty("warning", True)
                self.review_badge.setProperty("success", False)
            self._refresh_badge_style()
            self.recalculate()
        finally:
            self.profit_binder._loading_record = False
        self._refresh_edit_mode_ui()
        self.mark_saved()

    def _refresh_edit_mode_ui(self) -> None:
        """按新建/历史编辑模式刷新保存按钮文案与编辑状态提示。"""
        editing = self.editing_record_id is not None
        self.btn_save_record.setText("更新此记录" if editing else "保存本次记录")
        self.edit_state_label.setText("正在编辑历史记录" if editing else "")
        self.edit_state_label.setVisible(editing)

    @staticmethod
    def _fill_package_fields(fields: dict[str, Any], raw: dict[str, Any]) -> None:
        """把包装 dict 写入卡片字段（缺失归一为 0/空）。"""
        raw = raw if isinstance(raw, dict) else {}
        method_text = str(raw.get("packaging_method") or "")
        if fields.get("name") == "AI估算":
            # 仅显示层中文化：AI 英文包装方式转中文，原始 payload 不变
            method_text = packaging_method_zh(method_text)
        fields["method"].setText(method_text)
        fields["length"].setValue(float(raw.get("length_cm") or 0))
        fields["width"].setValue(float(raw.get("width_cm") or 0))
        fields["height"].setValue(float(raw.get("height_cm") or 0))
        fields["weight"].setValue(float(raw.get("weight_g") or 0))

    def set_product_link(self, link: str) -> None:
        if self.product_link is not None and link.strip():
            self.product_link.setText(link.strip())

    def refresh_settings(self) -> None:
        self.settings = self.context.settings_service.load()
        self.selected_forwarder_id = str(self.settings.get("selected_forwarder_id") or self.selected_forwarder_id)
        self.selected_profit_rule_id = str(self.settings.get("selected_profit_rule_id") or self.selected_profit_rule_id)
        self._updating = True
        self.tail_fee_usd.setValue(float(self.settings.get("default_tail_fee_usd", 5.56)))
        self._updating = False
        # 重新同步 RMB = USD × 当前有效汇率，确保汇率变化后一致性
        self._sync_tail_rmb_from_usd(recalculate=False)
        self.rebuild_quote_cards()
        if hasattr(self, "actual_forwarder_combo"):
            self._reload_actual_forwarder_combo()
        self.profit_binder.set_exchange_rate(float(self.settings.get("exchange_rate_usd_to_rmb", 7.2)))
        self.profit_binder.set_selected_rule_id(self.selected_profit_rule_id)
        self.profit_binder.set_rules(tuple(
            rule for rule in self.context.settings_service.rules_from_settings(self.settings)
            if rule.enabled and not rule.archived
        ))
        self.recalculate()
