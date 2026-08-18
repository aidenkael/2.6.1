"""UU测算 —— 轻量核算窗口。

独立启动，但工程上共享主软件内核：复用 ``AppContext`` / ``SettingsService`` /
``CalculationService`` / 确定性物流引擎 / ``CalculationBinder`` 双场景 driver
状态机；不复制、不重写任何物流/利润/汇率/货代/规则公式。

布局基准：``forms/quick_calculator.ui``（用户提供的 UU测算_轻量版.ui）。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDoubleSpinBox, QLabel, QMainWindow, QPushButton, QToolButton

from profit_accounting_26.application import AppContext
from profit_accounting_26.application.calculation_service import CalculationService
from profit_accounting_26.domain.models import PackageSpec
from profit_accounting_26.shared import resource_path
from profit_accounting_26.ui.binders.calculation_binder import CalculationBinder
from profit_accounting_26.ui.ui_loader import load_ui

# 蓝色 U 图标（仓库已有资产，直接复用，禁止重新设计）
QUICK_ICON_RELATIVE = "src/profit_accounting_26/ui/assets/uu_logo_blue.png"

# 最多展示 3 个启用货代的按钮（.ui 已预留）
_FORWARDER_BUTTON_NAMES = ("btnQuickForwarder1", "btnQuickForwarder2", "btnQuickForwarder3")
# 与主软件 ForwarderCardsController 相同的展示优先级
_FORWARDER_PRIORITY = {"义乌货代": 0, "深圳货代": 1}


class QuickCalculatorWindow(QMainWindow):
    """UU测算 主窗口：从 quick_calculator.ui 加载布局，直接复用现有 Binder/Service。

    与 UU护航 共用同一个数据目录 / location.json / SettingsService / AppContext；
    本窗口不写历史、不写设置（货代/尾程/规则选择只作用于本次测算会话）。
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
        # 蓝色 U 图标（任务栏/标题栏与主软件黑色 U 完全独立）
        self.setWindowIcon(QIcon(str(resource_path(QUICK_ICON_RELATIVE))))
        # 保持 .ui 固定紧凑尺寸（700×560）
        self.setFixedSize(loaded.minimumSize())
        # §7：默认保持置顶（不新增置顶开关）
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._find_widgets()
        self._wire_inputs()
        self._wire_forwarders()
        self._wire_clear()

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
        # 尾程双币种（RMB/USD 均可编辑，双向换算）
        self.tail_fee_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightRmb")
        self.tail_fee_usd: QDoubleSpinBox = f(QDoubleSpinBox, "spinTailFreightUsd")
        self.btn_clear: QPushButton = f(QPushButton, "btnClearAndNew")
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
        # 尾程：RMB/USD 双向换算，与主软件一致（USD 实时联动 RMB）
        self.tail_fee_usd.valueChanged.connect(lambda _value: self._on_tail_usd_live())
        self.tail_fee_usd.editingFinished.connect(lambda: self._on_tail_commit())
        self.tail_fee_rmb.editingFinished.connect(lambda: self._on_tail_rmb_commit())

    def _wire_forwarders(self) -> None:
        for button in self._forwarder_buttons:
            button.clicked.connect(self._on_forwarder_clicked)

    def _wire_clear(self) -> None:
        self.btn_clear.clicked.connect(self.clear_new)

    # ------------------------------------------------------------------
    # 尾程双币种（主软件语义：RMB=USD×汇率；只改会话，不写全局设置）
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

    def _on_tail_rmb_commit(self) -> None:
        if self._loading:
            return
        rate = self._rate()
        from PySide6.QtCore import QSignalBlocker

        with QSignalBlocker(self.tail_fee_usd):
            self.tail_fee_usd.setValue(round(self.tail_fee_rmb.value() / rate, 2) if rate else 0.0)
        self._recalculate()

    def _on_tail_commit(self) -> None:
        if not self._loading:
            self._recalculate()

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
        """与主软件 recalculate 相同的货代简名逻辑（如“深圳货代”→“深圳”）。"""
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
                button.setVisible(False)  # 不存在的位置不留占位
            button.setProperty("selected", button.property("forwarderId") == self.selected_forwarder_id)
            button.style().unpolish(button)
            button.style().polish(button)

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
        # 系统总成本 = 国内成本 + 物流总额（头程+服务费+尾程），与主软件数学等价；
        # 通过现有 CalculationBinder 入口传入，不另写第二套成本公式。
        system_cost = round(self.spin_domestic_cost.value() + quote.total_logistics_rmb, 2)
        self.profit_binder.set_calculation_cost(system_cost)
        self._current_system_cost = system_cost

    def _clear_results(self) -> None:
        self.txt_first_mile_total.setValue(0.0)
        self.profit_binder.set_calculation_cost(0.0)
        self._current_system_cost = 0.0

    # ------------------------------------------------------------------
    # 清空（只清当前会话）
    # ------------------------------------------------------------------

    def clear_new(self) -> None:
        """清空本次轻量核算会话：尺寸/重量/国内成本清零，利润区走 Binder.reset()
        （恢复活动预留 15%、活动后利润率 25%）；尾程沿用当前设置值（不恢复硬编码）；
        利润规则沿用当前设置选择；不写历史、不写设置、不删主软件数据。"""
        self._loading = True
        try:
            for spin in (self.spin_length, self.spin_width, self.spin_height,
                         self.spin_weight, self.spin_domestic_cost):
                spin.setValue(0.0)
        finally:
            self._loading = False
        self.profit_binder.reset()
        # reset() 期间“标价利率”控件的 valueChanged 会改写 Binder 内部 driver
        # （共享 Binder 既有行为：仅当该控件清空前非 0 才触发，主软件 clear_new
        # 因先触发成本=0 的刷新而天然规避）。这里按 §6 清空语义显式恢复
        # 活动后利润率 25%（与主软件“清空后 25%”一致）。
        if self.profit_binder.spin_profit_rate is not None:
            self.profit_binder.spin_profit_rate.setValue(25.0)
        self._recalculate()

    # ------------------------------------------------------------------
    # 设置刷新（§10 最小处理：启动/获得焦点时重读设置，不开发 IPC）
    # ------------------------------------------------------------------

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowActivate:
            self._refresh_settings_from_disk()

    def _refresh_settings_from_disk(self) -> None:
        """主软件修改设置后，Quick 重新加载（汇率/规则/尾程/货代）。"""
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
