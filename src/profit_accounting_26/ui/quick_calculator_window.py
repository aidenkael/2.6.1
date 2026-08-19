"""UU测算 —— 轻量核算窗口。

独立启动，但工程上共享主软件内核：复用 ``AppContext`` / ``SettingsService`` /
``CalculationService`` / 确定性物流引擎 / ``CalculationBinder`` 双场景 driver
状态机；不复制、不重写任何物流/利润/汇率/货代/规则公式。

Quick 只拥有：UI / 输入适配 / 显示映射 / 货代按钮 / 置顶 / 清空 / 启动入口。
"国内成本"是 Quick 专属合并输入（= 主软件商品成本 + 国内运费），
仅作 UI 输入适配，不要求主软件同形，也不写回主软件数据结构。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QToolButton,
)

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calculation_service import CalculationService
from profit_accounting_26.application.profit_defaults import apply_profit_defaults
from profit_accounting_26.domain.models import PackageSpec
from profit_accounting_26.engines.logistics import calculate_system_cost
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
from profit_accounting_26.ui.input_editing import install_first_click_select_all
from profit_accounting_26.ui.ui_loader import load_ui

# 蓝色 U 图标（仓库已有资产，直接复用，禁止重新设计）
QUICK_ICON_RELATIVE = "src/profit_accounting_26/ui/assets/uu_logo_blue.png"

# 最多展示 3 个启用货代的按钮（.ui 已预留）
_FORWARDER_BUTTON_NAMES = ("btnQuickForwarder1", "btnQuickForwarder2", "btnQuickForwarder3")
# 与主软件 ForwarderCardsController 相同的展示优先级
_FORWARDER_PRIORITY = {"义乌货代": 0, "深圳货代": 1}

# 顶层窗口固定尺寸契约（实机验收 448×475 无裁剪）。
# 硬规则：窗口创建时一次性测量并锁定两个稳定尺寸（collapsed / expanded），
# 之后折叠/展开只在两个固定尺寸之间切换；任何业务交互（数值变化/利润变化/
# 货代选择/货代数量刷新/WindowActivate/settings reload）永远不得再改变顶层尺寸，
# 也禁止用业务内容 sizeHint 重新推导窗口尺寸（杜绝尺寸正反馈漂移）。
QUICK_WINDOW_WIDTH = 448
QUICK_WINDOW_HEIGHT = 475
# 折叠分界：总成本区域（forwarderCostSection）下方；折叠时隐藏利润/活动区域
_COLLAPSIBLE_SECTION_NAMES = ("noActivitySection", "activitySection", "bottomSection")
# 规则状态标签固定尺寸（紧凑文本只有 已触发/未触发 三字，8pt 下三字宽约 33px，
# 44px 为含余量的精确固定宽，不超出标题行可用宽；一次设定永不更新；
# 禁止 setFixedWidth(sizeHint()+N) 追踪——QLabel sizeHint 会吸收既有固定宽度，
# 追踪会形成每轮 +N 的正反馈漂移，是本轮 P0 的尺寸漂移放大器）
_STATUS_LABEL_FIXED_WIDTH = 44
_STATUS_LABEL_FIXED_HEIGHT = 14


class QuickCalculatorWindow(QMainWindow):
    """UU测算 主窗口：从 quick_calculator.ui 加载布局，直接复用现有 Binder/Service。

    与 UU护航 共用同一个数据目录 / location.json / SettingsService / AppContext；
    本窗口不写历史、不写设置（货代/尾程/规则/利润默认值只作用于本次测算会话，
    绝不覆盖主软件保存的默认值）。
    """

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context
        self.calculation_service = CalculationService()
        self.settings: dict[str, Any] = dict(context.settings_service.load())
        self._loading = False
        self.selected_forwarder_id = str(self.settings.get("selected_forwarder_id") or "")

        loaded = load_ui("quick_calculator.ui")
        central = loaded.centralWidget()
        central.setParent(self)
        self.setCentralWidget(central)
        # 窗口名称固定为 .ui 的 windowTitle（UU测算）
        self.setWindowTitle(loaded.windowTitle())
        # .ui 的全局 stylesheet 在 loaded widget 上；转移到 self 使 property selector 生效
        self.setStyleSheet(loaded.styleSheet())
        # 蓝色 U 图标（任务栏/标题栏与主软件黑色 U 完全独立）
        self.setWindowIcon(QIcon(str(resource_path(QUICK_ICON_RELATIVE))))

        # 利润区 Grid → HBox 重组（消灭中间大空白）——必须在 findChild 前完成
        self._restructure_profit_section("noActivitySection", "noActivityGrid")
        self._restructure_profit_section("activitySection", "activityGrid")

        self._find_widgets()
        self._wire_inputs()
        self._wire_forwarders()
        self._wire_clear()
        self._wire_on_top()
        self._wire_collapse()

        # 利润区直接复用现有 CalculationBinder（UI 已按主软件相同 objectName 命名）
        self.profit_binder = CalculationBinder(self, context)
        self.profit_binder.set_exchange_rate(self._rate())
        self.profit_binder.set_selected_rule_id(
            str(self.settings.get("selected_profit_rule_id") or "")
        )
        self.profit_binder.set_rules(tuple(
            rule for rule in context.settings_service.rules_from_settings(self.settings)
            if rule.enabled and not rule.archived
        ))
        # 三项利润字段（活动预留/标价利率/活动后利润率）读取主软件
        # "明确保存后沿用"的同一套默认值；从未保存则沿用现有初始默认（15%/25%）。
        apply_profit_defaults(self.settings, self.profit_binder)

        self._refresh_forwarder_buttons()
        # 尾程初始值沿用当前设置/最近保存值（与主软件 refresh_settings 一致），
        # 不因清空恢复成硬编码。
        self._loading = True
        try:
            self.tail_fee_usd.setValue(float(self.settings.get("default_tail_fee_usd", 5.56)))
            self.tail_fee_rmb.setValue(float(self.settings.get("default_tail_fee_rmb", 0.0)))
        finally:
            self._loading = False
        self._sync_tail_rmb_from_usd(recalculate=False)

        self._recalculate()
        # 默认置顶（checkbox 默认勾选）
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        # 折叠/展开：初始化时一次性测量两个稳定尺寸并锁定（默认折叠）
        self._expanded = False
        self._collapsed_height = 0
        self._expanded_height = 0
        self._measure_window_sizes()
        self._set_details_visible(False)
        self._apply_locked_window_size()
        # 首次点击全选（主软件 / UU测算 共享同一公共实现）
        self._first_click_select_all_guard = install_first_click_select_all(self)
        # 两个规则状态标签固定尺寸一次设定（替代此前的 sizeHint 追踪）
        for label in (self.profit_binder.lbl_na_status, self.profit_binder.lbl_act_status):
            if label is not None:
                label.setFixedSize(_STATUS_LABEL_FIXED_WIDTH, _STATUS_LABEL_FIXED_HEIGHT)

    # ------------------------------------------------------------------
    # 利润区 Grid → HBox 重组（消灭中间大空白）
    # ------------------------------------------------------------------

    def _restructure_profit_section(self, section_name: str, grid_name: str) -> None:
        """利润区 QGridLayout 紧凑化：各列 Maximum 策略 + 末尾 stretch 列。

        .ui 的 QGridLayout 默认 columnStretch=0,0,0，三列等分剩余空间。
        本方法在 .ui 加载后执行一次性调整：
        - 把列 0/1/2 的 widget 设为 Maximum 宽度策略
        - 在列 3 添加 stretch 列吸收剩余空间（只在最右侧）
        """
        section = self.findChild(QFrame, section_name)
        if section is None:
            return
        grid = section.findChild(QGridLayout, grid_name)
        if grid is None:
            return

        # 确保所有列中的 widget 使用 Maximum 宽度策略（不被 grid 拉宽）
        for col in range(grid.columnCount()):
            for row in range(grid.rowCount()):
                item = grid.itemAtPosition(row, col)
                if item is None:
                    continue
                w = item.widget()
                if w is not None:
                    w.setSizePolicy(QSizePolicy.Policy.Maximum, w.sizePolicy().verticalPolicy())

        # 添加 stretch 列到最右侧（列 3），吸收所有剩余空间
        grid.setColumnStretch(3, 1)
        # 确保原始三列不 stretch
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)

    # ------------------------------------------------------------------
    # 控件绑定
    # ------------------------------------------------------------------

    def _find_widgets(self) -> None:
        f = self.findChild
        self.spin_length: QDoubleSpinBox = f(QDoubleSpinBox, "spinConservativeLengthCm")
        self.spin_width: QDoubleSpinBox = f(QDoubleSpinBox, "spinConservativeWidthCm")
        self.spin_height: QDoubleSpinBox = f(QDoubleSpinBox, "spinConservativeHeightCm")
        self.spin_weight: QDoubleSpinBox = f(QDoubleSpinBox, "spinConservativeWeightG")
        # 轻量 UI 唯一新增输入：国内成本 = 主软件「商品成本 + 国内运费」视觉合并
        self.spin_domestic_cost: QDoubleSpinBox = f(QDoubleSpinBox, "spinQuickDomesticCostRmb")
        # 总头程展示（只读）：取自当前货代 quote 的 weight_fee + fixed_fee
        self.txt_first_mile_total: QDoubleSpinBox = f(QDoubleSpinBox, "txtQuickFirstMileTotalRmb")
        # 尾程：USD 可编辑，RMB 冻结（灰色结果 = USD × 汇率）
        self.tail_fee_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightRmb")
        self.tail_fee_usd: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightUsd")
        self.btn_clear: QPushButton = f(QPushButton, "btnClearAndNew")
        self.chk_stay_on_top: QCheckBox = f(QCheckBox, "chkQuickStayOnTop")
        # 折叠箭头（总成本区域右侧；▼=可展开 / ▲=可收起）
        self.btn_toggle_details: QToolButton = f(QToolButton, "btnQuickToggleDetails")
        # 折叠分界以下的利润/活动区域（折叠时隐藏；promotionReserveSection 已
        # 并入 noActivitySection 标题行，随 noActivitySection 一起隐藏）
        self._collapsible_sections = [
            f(QFrame, name) for name in _COLLAPSIBLE_SECTION_NAMES
        ]
        self._forwarder_buttons = [
            f(QToolButton, name) for name in _FORWARDER_BUTTON_NAMES
        ]

    def _rate(self) -> float:
        value = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2) or 7.2)
        return value if value > 0 else 7.2

    def _wire_inputs(self) -> None:
        # 上游（尺寸/重量/国内成本）变化 → 重算下游（总头程/总成本/利润区）
        for spin in (self.spin_length, self.spin_width, self.spin_height,
                     self.spin_weight, self.spin_domestic_cost):
            spin.valueChanged.connect(lambda _value: self._recalculate())
        # 尾程：仅 USD 可编辑 → 实时联动 RMB（RMB 为冻结结果）
        self.tail_fee_usd.valueChanged.connect(lambda _value: self._on_tail_usd_live())
        self.tail_fee_usd.editingFinished.connect(lambda: self._on_tail_commit())
        # 注意：tail_fee_rmb 为 readOnly，不连接 editingFinished（无反向驱动）

    def _wire_forwarders(self) -> None:
        for button in self._forwarder_buttons:
            button.clicked.connect(self._on_forwarder_clicked)

    def _wire_clear(self) -> None:
        self.btn_clear.clicked.connect(self.clear_new)

    def _wire_on_top(self) -> None:
        self.chk_stay_on_top.toggled.connect(self._on_stay_on_top_toggled)

    def _wire_collapse(self) -> None:
        self.btn_toggle_details.clicked.connect(self._toggle_details)

    # ------------------------------------------------------------------
    # 折叠 / 展开（稳定尺寸切换，绝不按当前尺寸累加推导）
    # ------------------------------------------------------------------

    def _measure_window_sizes(self) -> None:
        """初始化时一次性确定 collapsed / expanded 两个稳定高度（此后只切换，不重测）。

        - expanded 高度：展开状态下一次 adjustSize 实测（包含标题栏/边框）；
        - collapsed 高度：同一 frame 下按布局 sizeHint 差量计算
          （collapsed 内容高 + frame），不再二次 adjustSize——
          保证两个值都是静态常量，之后所有折叠/展开交互只调用
          ``_apply_locked_window_size`` 在这两个固定尺寸之间切换，
          不存在反复 adjustSize / sizeHint 正反馈 / 逐轮累加，宽度恒为 448。
        """
        layout = self.centralWidget().layout()
        self._set_details_visible(True)
        layout.invalidate()
        layout.activate()
        self.adjustSize()
        expanded_content = layout.sizeHint().height()
        self._expanded_height = max(self.height(), 1)
        self._set_details_visible(False)
        layout.invalidate()
        layout.activate()
        collapsed_content = layout.sizeHint().height()
        frame = self._expanded_height - expanded_content
        self._collapsed_height = max(collapsed_content + frame, 1)

    def _set_details_visible(self, visible: bool) -> None:
        for section in self._collapsible_sections:
            if section is not None:
                section.setVisible(visible)

    def _toggle_details(self) -> None:
        self._expanded = not self._expanded
        self._set_details_visible(self._expanded)
        self.btn_toggle_details.setText("▲" if self._expanded else "▼")
        self._apply_locked_window_size()

    def _apply_locked_window_size(self) -> None:
        """在 collapsed / expanded 两个固定尺寸之间切换（min == max == 448×H）。

        不依赖任何内容 sizeHint；折叠/展开交互、原生窗口重建（show /
        setWindowFlag）后都只重新声明当前状态的固定契约，幂等、无漂移。
        """
        height = self._expanded_height if self._expanded else self._collapsed_height
        self.setFixedSize(QUICK_WINDOW_WIDTH, height)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """原生窗口每次显示/重建后重新声明当前状态的固定尺寸契约（幂等）。"""
        super().showEvent(event)
        self._apply_locked_window_size()

    # ------------------------------------------------------------------
    # 规则状态紧凑映射（Quick 专用，不改 CalculationBinder / 主软件）
    # ------------------------------------------------------------------

    @staticmethod
    def _compact_rule_status(full_text: str) -> str:
        """Quick 专用：将完整规则状态映射为短状态（只显示 已触发/未触发）。

        映射规则：
        - 内部 "已触发 +¥20.33" → Quick "已触发"
        - 内部 "已调整 ¥20.33"  → Quick "已触发"（规则实际已作用）
        - 内部 "未触发"         → Quick "未触发"
        - 内部 "无规则" / 空    → Quick "未触发"
        """
        if not full_text:
            return "未触发"
        if "已触发" in full_text or "已调整" in full_text:
            return "已触发"
        return "未触发"

    def _apply_compact_rule_status(self) -> None:
        """将利润区两个规则状态标签覆盖为 Quick 短格式（运行时动态文本映射）。

        基础样式（灰色小字）由 .ui stylesheet 的 QLabel[status="true"] 提供；
        已触发时仅覆盖颜色为绿色（inline stylesheet 优先级高于全局）。
        """
        for label in (self.profit_binder.lbl_na_status, self.profit_binder.lbl_act_status):
            if label is not None:
                full = label.text()
                compact = self._compact_rule_status(full)
                if label.text() != compact:
                    label.setText(compact)
                # 已触发=绿色；未触发由全局 stylesheet 灰色兜底
                if compact == "已触发":
                    label.setStyleSheet("color:#168A58;")
                else:
                    label.setStyleSheet("")
                # 标签宽度在初始化时一次性固定，此处不再随 sizeHint 追踪

    # ------------------------------------------------------------------
    # 尾程（Quick 专属：USD 可编辑 → RMB 冻结结果；不修改主软件双向语义）
    # ------------------------------------------------------------------

    def _on_tail_usd_live(self) -> None:
        if self._loading:
            return
        self._sync_tail_rmb_from_usd(recalculate=True)

    def _sync_tail_rmb_from_usd(self, *, recalculate: bool) -> None:
        rate = self._rate()
        from PySide6.QtCore import QSignalBlocker

        with QSignalBlocker(self.tail_fee_rmb):
            self.tail_fee_rmb.setValue(round(self.tail_fee_usd.value() * rate, 2))
        if recalculate:
            self._recalculate()

    def _on_tail_commit(self) -> None:
        if not self._loading:
            self._recalculate()

    # ------------------------------------------------------------------
    # 置顶（默认勾选；可取消；不写入 settings，每次启动默认置顶）
    # ------------------------------------------------------------------

    def _on_stay_on_top_toggled(self, checked: bool) -> None:
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, bool(checked))
        # 部分平台切换 flag 会把窗口隐藏，这里确保切换后窗口保持可见
        self.show()

    # ------------------------------------------------------------------
    # 货代选择（最多 3 个；只改本次测算，不写全局默认货代）
    # ------------------------------------------------------------------

    def _enabled_forwarders(self) -> list:
        forwarders = self.context.settings_service.forwarders_from_settings(self.settings)
        enabled = [item for item in forwarders if item.enabled and not item.archived]
        enabled.sort(key=lambda item: (_FORWARDER_PRIORITY.get(item.name, 9), item.name))
        return enabled[:3]

    @staticmethod
    def _short_name(name: str) -> str:
        """与主软件 recalculate 相同的货代简名逻辑（如"深圳货代"→"深圳"）。"""
        return str(name or "").rstrip("货代") or str(name or "")

    def _refresh_forwarder_buttons(self) -> None:
        enabled = self._enabled_forwarders()
        visible_ids = {item.id for item in enabled}
        if self.selected_forwarder_id not in visible_ids:
            self.selected_forwarder_id = enabled[0].id if enabled else ""
        for index, button in enumerate(self._forwarder_buttons):
            if index < len(enabled):
                forwarder = enabled[index]
                button.setText(self._short_name(forwarder.name))
                button.setProperty("forwarderId", forwarder.id)
                button.setVisible(True)
            else:
                button.setProperty("forwarderId", "")
                button.setVisible(False)  # 不存在的位置隐藏，窗口尺寸不变
            button.setProperty("selected", button.property("forwarderId") == self.selected_forwarder_id)
            button.style().unpolish(button)
            button.style().polish(button)
        # 注意：不调用任何 resize / adjustSize —— 窗口尺寸在初始化时已固定

    def _on_forwarder_clicked(self) -> None:
        forwarder_id = str(self.sender().property("forwarderId") or "")
        if forwarder_id and forwarder_id != self.selected_forwarder_id:
            self.selected_forwarder_id = forwarder_id
            for button in self._forwarder_buttons:
                selected = button.property("forwarderId") == forwarder_id
                if button.property("selected") != selected:
                    button.setProperty("selected", selected)
                    button.style().unpolish(button)
                    button.style().polish(button)
            self._recalculate()

    # ------------------------------------------------------------------
    # 计算链（只复用，不重写）
    # ------------------------------------------------------------------

    def _recalculate(self) -> None:
        if self._loading:
            return
        length = self.spin_length.value()
        width = self.spin_width.value()
        height = self.spin_height.value()
        weight = self.spin_weight.value()
        enabled = self._enabled_forwarders()
        if length <= 0 or width <= 0 or height <= 0 or weight <= 0 or not enabled:
            self._clear_results()
            return
        package = PackageSpec(length_cm=length, width_cm=width, height_cm=height, weight_g=weight)
        quotes = self.calculation_service.quote_all_forwarders(
            package=package,
            forwarders=enabled,
            tail_fee_rmb=self.tail_fee_rmb.value(),
        )
        if self.selected_forwarder_id not in quotes:
            self.selected_forwarder_id = enabled[0].id
        quote = quotes[self.selected_forwarder_id]
        # 总头程展示 = weight_fee + fixed_fee（取自现有 LogisticsQuote，不重新计算）
        self.txt_first_mile_total.setValue(round(quote.weight_fee_rmb + quote.fixed_fee_rmb, 2))
        # 系统总成本：直接调用共享 system-cost 计算入口（calculate_system_cost），
        # Quick 的"国内成本"作为合并输入传入（product_cost_rmb 槽位）——
        # 数学上与主软件"商品成本+国内运费+物流总额"等价；以后物流/成本公式
        # 只在共享核心维护，Quick 自动跟随。
        system_cost = round(
            calculate_system_cost(
                product_cost_rmb=self.spin_domestic_cost.value(),
                domestic_shipping_rmb=0.0,
                logistics_total_rmb=quote.total_logistics_rmb,
            ),
            2,
        )
        self.profit_binder.set_calculation_cost(system_cost)
        self._current_system_cost = system_cost
        # Quick 规则状态紧凑映射（不改 Binder 内部计算）
        self._apply_compact_rule_status()

    def _clear_results(self) -> None:
        self.txt_first_mile_total.setValue(0.0)
        self.profit_binder.set_calculation_cost(0.0)
        self._current_system_cost = 0.0
        self._apply_compact_rule_status()

    # ------------------------------------------------------------------
    # 清空（只清当前会话）
    # ------------------------------------------------------------------

    def clear_new(self) -> None:
        """清空本次轻量核算会话：尺寸/重量/国内成本清零，利润区走 Binder.reset()，
        随后三项利润字段恢复"用户上一次在主软件明确保存"的默认值（从未保存则
        沿用现有初始默认 15%/25%）；尾程沿用当前设置值（不恢复硬编码）；利润规则
        沿用当前设置选择；不写历史、不写设置、不删主软件数据。"""
        self._loading = True
        try:
            for spin in (self.spin_length, self.spin_width, self.spin_height,
                         self.spin_weight, self.spin_domestic_cost):
                spin.setValue(0.0)
        finally:
            self._loading = False
        self.profit_binder.reset()
        apply_profit_defaults(self.settings, self.profit_binder)
        self._recalculate()

    # ------------------------------------------------------------------
    # 设置刷新（§10 最小处理：启动/获得焦点时重读设置，不开发 IPC）
    # ------------------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowActivate:
            self._refresh_settings_from_disk()

    def _refresh_settings_from_disk(self) -> None:
        """主软件修改设置后，Quick 重新加载（汇率/规则/尾程/货代）。

        三项利润默认值只在启动与"清空"时读取（与主软件一致：refresh_settings
        不触碰这 3 项）；Quick 会话内的临时修改绝不写回 settings。
        """
        fresh = self.context.settings_service.load()
        self.settings = dict(fresh)
        self.profit_binder.set_exchange_rate(self._rate())
        self.profit_binder.set_selected_rule_id(
            str(fresh.get("selected_profit_rule_id") or "")
        )
        self.profit_binder.set_rules(tuple(
            rule for rule in self.context.settings_service.rules_from_settings(fresh)
            if rule.enabled and not rule.archived
        ))
        self._loading = True
        try:
            self.tail_fee_usd.setValue(float(fresh.get("default_tail_fee_usd", 5.56)))
        finally:
            self._loading = False
        self._sync_tail_rmb_from_usd(recalculate=False)
        self._refresh_forwarder_buttons()
        self._recalculate()
