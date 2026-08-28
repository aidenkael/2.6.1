"""测算页利润区 Binder —— 双场景 driver 状态机。

绑定 ``main_window.ui`` 中 ``pageCalculation`` 的利润区字段，实现：

- 无活动 / 活动后双场景利润计算；
- driver 状态机：用户同一时间只编辑一个字段，该字段成为当前主输入；
- 防递归保护（``_profit_updating`` + ``QSignalBlocker``）；
- 冻结 / 可编辑状态（RMB 上 USD 下，冻结字段随汇率/成本/售价实时变化）；
- 两场景规则独立判断，状态标签 + tooltip 明细；
- SHEIN 核价比较（仅显示，不参与利润公式）。

**不**包含：AI 识图、包装估算、货代报价——这些仍由现有 CalculationPage 逻辑处理，
本 Binder 只负责利润区。
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLabel

from profit_accounting_26.application import AppContext
from profit_accounting_26.domain.rules import AdjustmentRule
from profit_accounting_26.engines.profit import (
    calculate_dual_profit,
    sale_price_for_dual_activity_target,
    sale_price_for_scenario_target_profit,
)


# driver 取值
DRIVER_PROFIT_RATE = "profit_rate"
DRIVER_NO_ACTIVITY_PRICE = "no_activity_price"
DRIVER_NO_ACTIVITY_PROFIT = "no_activity_profit"
DRIVER_NO_ACTIVITY_PROFIT_RATE = "no_activity_profit_rate"
DRIVER_ACTIVITY_PROFIT = "activity_profit"

_VALID_DRIVERS = (
    DRIVER_PROFIT_RATE,
    DRIVER_NO_ACTIVITY_PRICE,
    DRIVER_NO_ACTIVITY_PROFIT,
    DRIVER_NO_ACTIVITY_PROFIT_RATE,
    DRIVER_ACTIVITY_PROFIT,
)

# 规则下拉特殊选项：全部启用规则同时参与计算
ALL_ENABLED_RULES_ID = "__all_enabled__"

# 颜色常量
_COLOR_NORMAL = "#607089"
_COLOR_TRIGGERED_INCOME = "#168A58"  # 绿色：增加收入
_COLOR_TRIGGERED_COST = "#C77600"  # 警示色：增加成本

DEFAULT_RESERVE_PERCENT = 15.0
DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT = 25.0


class CalculationBinder(QObject):
    """利润区双场景 Binder。

    在 CalculationPage 完成 .ui 加载后，传入 pageCalculation widget 进行绑定。
    """

    profitChanged = Signal()  # 利润区数据变化时发射，供 CalculationPage 同步记录 payload
    selectedRuleChanged = Signal(str)  # 利润规则选择变化，供页面持久化到 settings

    def __init__(self, page: QWidget, context: AppContext) -> None:
        super().__init__(page)
        self.page = page
        self.context = context
        self.settings = context.settings_service.load()

        # 利润区状态
        self._profit_updating = False
        self._profit_driver: str = DRIVER_PROFIT_RATE
        self._calculation_total_cost_rmb: float = 0.0
        self._exchange_rate: float = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        self._shein_quote_usd: float = 0.0
        self._reserve_percent: float = DEFAULT_RESERVE_PERCENT
        self._no_activity_price_usd: float = 0.0
        self._rules: tuple[AdjustmentRule, ...] = ()
        self._selected_rule_id: str = ""
        # 记录快照加载标志：load_from_record 后置位，供页面判断历史/当前推算
        self._snapshot_loaded = False
        self._snapshot_legacy = False
        # 旧记录兼容状态是否已被用户明确操作退出
        # （编辑利润区字段/修改系统成本/主动重算）
        self._legacy_exited = False
        # 记录加载保护状态：load_record_payload 开始时置 True，
        # 内部 recalculate/set_calculation_cost 不得退出快照；
        # 恢复结束后在 finally 中置 False。
        self._loading_record = False
        # 旧记录原始利润快照：load_from_record 时保存，export 时原样输出
        # 不重新推导售价/利润/利润率
        self._legacy_snapshot: dict[str, Any] | None = None
        # 快照显示模式：记录加载后保持保存时界面结果，自动重算只做冻结换算
        # 显示，不按当前设置静默重算双场景；用户主动编辑利润区字段后退出
        # 该模式，之后的计算属当前推算。
        self._snapshot_display_mode = False
        # 打开记录时捕获的当前设置状态（汇率/规则/选中规则），退出快照模式时恢复。
        # 注意：计算总成本是上游状态，不属于“当前设置”，退出快照时永不恢复、
        # 永不被下游利润字段编辑隐式改写（成本所有权见 set_calculation_cost）。
        self._live_exchange_rate: float | None = None
        self._live_rules: tuple[AdjustmentRule, ...] | None = None
        self._live_selected_rule_id: str | None = None

        # 查找所有利润区控件
        self._find_widgets()
        self._sync_initial_values()
        self._setup_frozen_states()
        self._connect_signals()
        self._refresh_all()

    def _sync_initial_values(self) -> None:
        """从 .ui 控件读取初始值，同步到内部状态。

        新建记录的业务默认值固定为活动预留 15%、活动后利润率 25%。
        此方法在信号连接前执行，不会被误判为用户编辑。
        """
        if self.spin_reserve:
            self.spin_reserve.setValue(DEFAULT_RESERVE_PERCENT)
            self._reserve_percent = DEFAULT_RESERVE_PERCENT
        if self.spin_profit_rate:
            self.spin_profit_rate.setValue(DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT)
        if self.txt_shein_usd:
            self._shein_quote_usd = self.txt_shein_usd.value()
        if self.txt_na_price_usd:
            self._no_activity_price_usd = self.txt_na_price_usd.value()
        if self.txt_cost_rmb:
            self._calculation_total_cost_rmb = self.txt_cost_rmb.value()

    # ------------------------------------------------------------------
    # 控件查找
    # ------------------------------------------------------------------

    def _find_widgets(self) -> None:
        f = self.page.findChild
        # SHEIN 核价
        self.txt_shein_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtSheinPriceRmb")
        self.txt_shein_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtSheinPriceUsd")
        # 计算总成本
        self.txt_cost_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtCalculatedCostRmb")
        self.txt_cost_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtCalculatedCostUsd")
        # 利润率
        self.spin_profit_rate: QDoubleSpinBox = f(QDoubleSpinBox, "spinProfitRate")
        # 无活动售价
        self.txt_na_price_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtNoActivityPriceRmb")
        self.txt_na_price_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtNoActivityPriceUsd")
        # 无活动利润
        self.txt_na_profit_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtNoActivityProfitRmb")
        self.txt_na_profit_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtNoActivityProfitUsd")
        # 活动预留
        self.spin_reserve: QDoubleSpinBox = f(QDoubleSpinBox, "spinPromotionReserve")
        # 活动后售价
        self.txt_act_price_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtActivityPriceRmb")
        self.txt_act_price_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtActivityPriceUsd")
        # 活动后利润
        self.txt_act_profit_rmb: QDoubleSpinBox = f(QDoubleSpinBox, "txtActivityProfitRmb")
        self.txt_act_profit_usd: QDoubleSpinBox = f(QDoubleSpinBox, "txtActivityProfitUsd")
        # 规则状态标签
        self.lbl_na_status: QLabel = f(QLabel, "lblNoActivitySubsidyStatus")
        self.lbl_act_status: QLabel = f(QLabel, "lblActivitySubsidyStatus")
        # 规则选择
        self.cmb_rule: QComboBox = f(QComboBox, "cmbProfitRule")
        # 利润结论
        self.lbl_conclusion: QLabel = f(QLabel, "lblProfitConclusion")

        # 标价利率（正式写入 main_window.ui，可编辑百分比输入）
        self.lbl_list_price_rate_title: QLabel = f(QLabel, "lblListPriceProfitRateTitle")
        self.txt_list_price_rate: QDoubleSpinBox = f(QDoubleSpinBox, "txtListPriceProfitRate")
        self.unit_list_price_rate: QLabel = f(QLabel, "unit_txtListPriceProfitRate")

    def _setup_frozen_states(self) -> None:
        """设置冻结字段为只读。

        冻结表（契约 §7）：
        - SHEIN 核价 RMB：冻结换算
        - 计算总成本 USD：冻结换算
        - 无活动售价 RMB：冻结换算
        - 无活动利润 USD：冻结换算
        - 活动后售价 RMB/USD：冻结计算
        - 活动后利润 USD：冻结换算
        """
        frozen_widgets = [
            self.txt_shein_rmb,
            self.txt_cost_usd,
            self.txt_na_price_rmb,
            self.txt_na_profit_usd,
            self.txt_act_price_rmb,
            self.txt_act_price_usd,
            self.txt_act_profit_usd,
        ]
        for widget in frozen_widgets:
            if widget:
                widget.setReadOnly(True)
                # 冻结字段视觉提示：浅灰背景
                pal = widget.palette()
                pal.setColor(QPalette.ColorRole.Base, QColor("#f1f5fa"))
                widget.setPalette(pal)

        # 显式范围：.ui 未全部声明 min/max，不能依赖 Qt 默认值（0–99.99）
        range_specs = [
            (self.txt_shein_usd, 0.0, 1_000_000.0),
            (self.txt_shein_rmb, 0.0, 10_000_000.0),
            (self.txt_cost_rmb, 0.0, 10_000_000.0),
            (self.txt_cost_usd, 0.0, 10_000_000.0),
            (self.txt_na_price_usd, 0.0, 1_000_000.0),
            (self.txt_na_price_rmb, 0.0, 10_000_000.0),
            (self.txt_act_price_usd, 0.0, 1_000_000.0),
            (self.txt_act_price_rmb, 0.0, 10_000_000.0),
            (self.spin_profit_rate, -10_000.0, 10_000.0),
            (self.txt_list_price_rate, -10_000.0, 10_000.0),
            (self.spin_reserve, 0.0, 99.0),
        ]
        for widget, lo, hi in range_specs:
            if widget:
                widget.setRange(lo, hi)

        # 利润相关字段允许负值（亏损场景）
        profit_widgets = [
            self.txt_na_profit_rmb,
            self.txt_na_profit_usd,
            self.txt_act_profit_rmb,
            self.txt_act_profit_usd,
            self.spin_profit_rate,
            self.txt_list_price_rate,
        ]
        for widget in profit_widgets:
            if widget:
                widget.setMinimum(-999999.99)

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """连接可编辑字段的 valueChanged 信号。每个信号只连接一次。"""
        editable_bindings = [
            (self.txt_shein_usd, self._on_shein_quote_changed),
            (self.txt_cost_rmb, self._on_calc_cost_changed),
            (self.spin_profit_rate, self._on_profit_rate_changed),
            (self.txt_list_price_rate, self._on_list_price_rate_changed),
            (self.txt_na_price_usd, self._on_na_price_changed),
            (self.txt_na_profit_rmb, self._on_na_profit_changed),
            (self.spin_reserve, self._on_reserve_changed),
            (self.txt_act_profit_rmb, self._on_act_profit_changed),
        ]
        for widget, handler in editable_bindings:
            if widget:
                widget.valueChanged.connect(handler)

        if self.cmb_rule:
            self.cmb_rule.currentIndexChanged.connect(self._on_rule_changed)

    # ------------------------------------------------------------------
    # 外部数据注入
    # ------------------------------------------------------------------

    def set_exchange_rate(self, rate: float) -> None:
        """汇率变化时更新冻结换算。

        快照显示模式下只记录当前设置汇率，不改写保存时快照。
        """
        if rate <= 0:
            return
        if self._snapshot_display_mode:
            self._live_exchange_rate = rate
            return
        self._exchange_rate = rate
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def set_calculation_cost(self, cost_rmb: float) -> None:
        """上方成本变化时覆盖利润区计算总成本（成本唯一合法来源之一）。

        ``calculation_total_cost_rmb`` 是上游状态，只允许两条变更路径：
        1. CalculationPage 因上游成本输入变化而显式调用本方法；
        2. 用户显式编辑计算成本输入（_on_calc_cost_changed）。
        下游利润字段编辑退出快照时绝不改写/恢复成本。

        快照显示模式下：系统总成本变化属于"明确操作"，立即退出历史
        快照模式，将新成本覆盖利润区计算总成本，按当前有效 driver
        重新计算双场景利润，并标记为"当前推算（非历史快照）"。

        记录加载保护：``_loading_record=True`` 期间（load_record_payload
        内部 recalculate/set_calculation_cost），不退出快照也不改写成本，
        直接忽略；不依赖浮点成本相等判断。
        """
        cost_rmb = max(0.0, float(cost_rmb))
        if self._snapshot_display_mode:
            if self._loading_record:
                # 记录加载期间：程序化调用不退出快照，也不改写快照成本
                return
            # 加载完成后系统成本变化 → 退出快照，按新成本重算
            self._exit_snapshot_mode()
        self._calculation_total_cost_rmb = cost_rmb
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def set_selected_rule_id(self, rule_id: str) -> None:
        self._selected_rule_id = rule_id
        self._refresh_rule_combo()

    def set_rules(self, rules) -> None:
        """设置利润规则列表（来自 SettingsService）。

        快照显示模式下只记录当前设置规则，不改写保存时规则快照。
        """
        rules = tuple(rules)
        if self._snapshot_display_mode:
            self._live_rules = rules
            return
        self._rules = rules
        self._refresh_rule_combo()
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    @property
    def selected_rule_id(self) -> str:
        return self._selected_rule_id

    def is_in_snapshot_mode(self) -> bool:
        """是否处于历史快照或旧记录兼容状态（未被用户明确操作退出）。

        build_record_payload 据此判断是否使用 profit_scenarios 快照值
        而非当前 settings/current_system_cost。
        """
        return self._snapshot_display_mode

    def set_shein_quote_usd(self, value: float) -> None:
        """外部（记录加载/清空）设置 SHEIN 核价 USD。"""
        if self.txt_shein_usd:
            self.txt_shein_usd.setValue(float(value))
        self._shein_quote_usd = float(value)

    def reset(self) -> None:
        """清空并新建时复位利润区，并恢复 15% / 25% 业务默认值。"""
        self._snapshot_display_mode = False
        self._snapshot_loaded = False
        self._snapshot_legacy = False
        self._legacy_exited = False
        self._loading_record = False
        self._legacy_snapshot = None
        self._profit_driver = DRIVER_PROFIT_RATE
        self._calculation_total_cost_rmb = 0.0
        self._no_activity_price_usd = 0.0
        self._shein_quote_usd = 0.0
        self._profit_updating = True
        try:
            for widget in (
                self.txt_shein_usd,
                self.txt_shein_rmb,
                self.txt_cost_rmb,
                self.txt_cost_usd,
                self.txt_na_price_usd,
                self.txt_na_price_rmb,
                self.txt_na_profit_rmb,
                self.txt_na_profit_usd,
                self.txt_act_price_usd,
                self.txt_act_price_rmb,
                self.txt_act_profit_rmb,
                self.txt_act_profit_usd,
                self.txt_list_price_rate,
            ):
                if widget:
                    widget.setValue(0.0)
            if self.spin_reserve:
                self.spin_reserve.setValue(DEFAULT_RESERVE_PERCENT)
            if self.spin_profit_rate:
                self.spin_profit_rate.setValue(DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT)
            self._reserve_percent = DEFAULT_RESERVE_PERCENT
        finally:
            self._profit_updating = False
        self._refresh_all()

    # ------------------------------------------------------------------
    # 规则下拉
    # ------------------------------------------------------------------

    def _refresh_rule_combo(self) -> None:
        if not self.cmb_rule:
            return
        with QSignalBlocker(self.cmb_rule):
            self.cmb_rule.clear()
            self.cmb_rule.addItem("不使用规则", "")
            for rule in self._rules:
                if rule.archived or not rule.enabled:
                    continue
                self.cmb_rule.addItem(rule.name, rule.id)
            # “全部启用规则”：全部启用规则同时参与计算（多规则合计）
            self.cmb_rule.addItem("全部启用规则", ALL_ENABLED_RULES_ID)
            # 选中当前规则
            idx = self.cmb_role_find(self._selected_rule_id)
            if idx >= 0:
                self.cmb_rule.setCurrentIndex(idx)

    def cmb_role_find(self, rule_id: str) -> int:
        if not self.cmb_rule:
            return -1
        for i in range(self.cmb_rule.count()):
            if self.cmb_rule.itemData(i) == rule_id:
                return i
        return -1

    def _active_rules(self) -> tuple[AdjustmentRule, ...]:
        """返回当前参与计算的规则。

        - 选择“全部启用规则”时返回全部启用且未归档规则（多规则合计）；
        - 否则返回下拉选中的单一规则。
        """
        if not self.cmb_rule:
            return ()
        rule_id = self.cmb_rule.currentData()
        if not rule_id:
            return ()
        if rule_id == ALL_ENABLED_RULES_ID:
            return tuple(r for r in self._rules if r.enabled and not r.archived)
        return tuple(r for r in self._rules if r.id == rule_id and r.enabled and not r.archived)

    def _on_rule_changed(self, _index: int) -> None:
        self._exit_snapshot_mode()
        self._selected_rule_id = self.cmb_rule.currentData() if self.cmb_rule else ""
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()
        self.selectedRuleChanged.emit(str(self._selected_rule_id))

    # ------------------------------------------------------------------
    # 核心刷新逻辑
    # ------------------------------------------------------------------

    def _refresh_all(self) -> None:
        """根据当前 driver 和状态，重算所有利润字段。

        防递归：如果 _profit_updating 为 True，直接返回。
        """
        if self._profit_updating:
            return
        if self._snapshot_display_mode:
            # 记录快照显示模式：保持保存时/恢复的界面结果，只更新冻结换算显示，
            # 不按当前设置重算双场景（不静默重算、不伪造活动场景历史），
            # 直到用户主动编辑利润区字段才退出该模式（属当前推算）。
            self._profit_updating = True
            try:
                self._do_display_only_refresh()
            finally:
                self._profit_updating = False
            self.profitChanged.emit()
            return
        self._profit_updating = True
        try:
            self._do_refresh()
        finally:
            self._profit_updating = False
        self.profitChanged.emit()

    def _do_display_only_refresh(self) -> None:
        """旧记录/快照显示模式：只刷新成本与 SHEIN 核价冻结换算，不重算双场景。

        同时更新标价利率（使用保存时的标价利润与保存时成本）。"""
        cost = self._calculation_total_cost_rmb
        rate = self._exchange_rate
        self._set_spin(self.txt_cost_rmb, cost)
        self._set_spin(self.txt_cost_usd, cost / rate if rate > 0 and cost > 0 else 0.0)
        shein_usd = self.txt_shein_usd.value() if self.txt_shein_usd else 0.0
        self._shein_quote_usd = shein_usd
        self._set_spin(self.txt_shein_rmb, shein_usd * rate if rate > 0 else 0.0)
        self._update_shein_comparison_from_values()
        # 标价利率：快照模式使用保存时的标价利润与保存时成本（派生显示，
        # 不退出快照模式；成本为 0 时安全显示 0，禁止异常）。
        if self.txt_list_price_rate is not None:
            na_profit_snap = self.txt_na_profit_rmb.value() if self.txt_na_profit_rmb else 0.0
            rate_value = (na_profit_snap / cost * 100.0) if cost > 0 else 0.0
            self._set_spin(self.txt_list_price_rate, rate_value)
        self._update_snapshot_status_label()

    def _do_refresh(self) -> None:
        driver = self._profit_driver
        rules = self._active_rules()
        cost = self._calculation_total_cost_rmb
        rate = self._exchange_rate
        reserve = self._reserve_percent
        na_price = self._no_activity_price_usd

        # 从 UI 读取当前 driver 的目标值。上游自动变化和 reserve 编辑会先
        # 把 driver 固定为当前活动后利润率；只有用户显式编辑售价/利润字段
        # 才进入对应的反推分支。
        if driver == DRIVER_PROFIT_RATE and self.spin_profit_rate:
            target_rate = self.spin_profit_rate.value() / 100.0
            if cost > 0:
                target_act_profit = cost * target_rate
                try:
                    na_price = sale_price_for_dual_activity_target(
                        total_cost_rmb=cost,
                        target_activity_profit_rmb=target_act_profit,
                        reserve_percent=reserve,
                        exchange_rate=rate,
                        rules=rules,
                    )
                except ValueError:
                    na_price = 0.0
            else:
                na_price = 0.0
                target_act_profit = 0.0
        elif driver == DRIVER_NO_ACTIVITY_PRICE and self.txt_na_price_usd:
            na_price = self.txt_na_price_usd.value()
        elif driver == DRIVER_NO_ACTIVITY_PROFIT and self.txt_na_profit_rmb:
            target_na_profit = self.txt_na_profit_rmb.value()
            try:
                na_price = sale_price_for_scenario_target_profit(
                    total_cost_rmb=cost,
                    target_profit_rmb=target_na_profit,
                    exchange_rate=rate,
                    rules=rules,
                    scenario="no_activity",
                )
            except ValueError:
                na_price = 0.0
        elif driver == DRIVER_NO_ACTIVITY_PROFIT_RATE and self.txt_list_price_rate:
            # 标价利率 = 标价利润 ÷ 计算总成本 × 100%；
            # 目标标价利润 = 计算总成本 × 标价利率 / 100，再复用单场景 solver 反推标价。
            target_na_profit = cost * self.txt_list_price_rate.value() / 100.0
            try:
                na_price = sale_price_for_scenario_target_profit(
                    total_cost_rmb=cost,
                    target_profit_rmb=target_na_profit,
                    exchange_rate=rate,
                    rules=rules,
                    scenario="no_activity",
                )
            except ValueError:
                na_price = 0.0
        elif driver == DRIVER_ACTIVITY_PROFIT and self.txt_act_profit_rmb:
            target_act_profit = self.txt_act_profit_rmb.value()
            try:
                na_price = sale_price_for_dual_activity_target(
                    total_cost_rmb=cost,
                    target_activity_profit_rmb=target_act_profit,
                    reserve_percent=reserve,
                    exchange_rate=rate,
                    rules=rules,
                )
            except ValueError:
                na_price = 0.0

        self._no_activity_price_usd = max(0.0, na_price)

        # 计算双场景
        if na_price > 0 and rate > 0:
            result = calculate_dual_profit(
                no_activity_price_usd=na_price,
                reserve_percent=reserve,
                total_cost_rmb=cost,
                exchange_rate=rate,
                rules=rules,
            )
            na = result.no_activity
            act = result.activity
            profit_rate = result.profit_rate
        else:
            # 无有效售价：安全显示空状态
            na = None
            act = None
            profit_rate = None

        # 更新 UI（冻结字段用 QSignalBlocker 避免递归）
        self._set_spin(self.txt_na_price_usd, na_price)
        self._set_spin(self.txt_na_price_rmb, na.sale_price_rmb if na else 0.0)
        self._set_spin(self.txt_act_price_usd, act.sale_price_usd if act else 0.0)
        self._set_spin(self.txt_act_price_rmb, act.sale_price_rmb if act else 0.0)
        self._set_spin(self.txt_na_profit_rmb, na.profit_rmb if na else 0.0)
        self._set_spin(self.txt_na_profit_usd, na.profit_usd if na else 0.0)
        self._set_spin(self.txt_act_profit_rmb, act.profit_rmb if act else 0.0)
        self._set_spin(self.txt_act_profit_usd, act.profit_usd if act else 0.0)
        self._set_spin(self.txt_cost_rmb, cost)
        self._set_spin(self.txt_cost_usd, cost / rate if rate > 0 and cost > 0 else 0.0)

        # 利润率只在显式售价/利润 driver 下反推；目标利润率 driver 保持用户输入。
        if driver != DRIVER_PROFIT_RATE and self.spin_profit_rate:
            rate_pct = (profit_rate * 100.0) if profit_rate is not None else 0.0
            self._set_spin(self.spin_profit_rate, rate_pct)

        # SHEIN 核价冻结换算
        shein_usd = self.txt_shein_usd.value() if self.txt_shein_usd else 0.0
        self._shein_quote_usd = shein_usd
        self._set_spin(self.txt_shein_rmb, shein_usd * rate if rate > 0 else 0.0)

        # 规则状态标签
        self._update_rule_status(na, act)

        # SHEIN 核价比较
        self._update_shein_comparison(na)

        # 标价利率 = 标价利润 RMB ÷ 计算总成本 RMB × 100%。
        # 只有标价利率自身作为 driver 时保持用户输入，其余 driver 派生显示。
        if driver != DRIVER_NO_ACTIVITY_PROFIT_RATE and self.txt_list_price_rate is not None:
            na_profit = na.profit_rmb if na else 0.0
            list_price_rate = (na_profit / cost * 100.0) if cost > 0 else 0.0
            self._set_spin(self.txt_list_price_rate, list_price_rate)

        # 快照状态提示（在核价比较之后，合并 tooltip）
        self._update_snapshot_status_label()

    @staticmethod
    def _set_spin(widget: QDoubleSpinBox | None, value: float) -> None:
        """安全设置 spinbox 值，带 QSignalBlocker 防递归。允许负值（利润亏损场景）。"""
        if widget is None:
            return
        with QSignalBlocker(widget):
            # 不截断负值；仅处理 None/NaN
            v = float(value) if value is not None and value == value else 0.0
            widget.setValue(v)

    # ------------------------------------------------------------------
    # 规则状态标签
    # ------------------------------------------------------------------

    def _update_rule_status(self, na, act) -> None:
        """更新两个规则状态标签 + tooltip。"""
        self._update_single_rule_status(self.lbl_na_status, na, "no_activity")
        self._update_single_rule_status(self.lbl_act_status, act, "activity")

    def _update_single_rule_status(self, label: QLabel | None, scenario_result, scenario: str) -> None:
        if label is None:
            return
        if scenario_result is None or not scenario_result.rule_evaluations:
            label.setText("无规则")
            label.setStyleSheet(f"color:{_COLOR_NORMAL};")
            label.setToolTip("")
            return

        # 过滤当前场景的规则评估
        evaluations = [e for e in scenario_result.rule_evaluations if e.scenario == scenario and e.matched]
        if not evaluations:
            label.setText("未触发")
            label.setStyleSheet(f"color:{_COLOR_NORMAL};")
            label.setToolTip("")
            return

        total_income = sum(e.amount_rmb for e in evaluations if e.direction == "income")
        total_cost_adj = sum(e.amount_rmb for e in evaluations if e.direction == "cost")
        net = total_income - total_cost_adj

        if net >= 0:
            label.setText(f"已触发 +¥{net:.2f}")
            label.setStyleSheet(f"color:{_COLOR_TRIGGERED_INCOME};font-weight:600;")
        else:
            label.setText(f"已调整 ¥{net:.2f}")
            label.setStyleSheet(f"color:{_COLOR_TRIGGERED_COST};font-weight:600;")

        # tooltip 列出每条规则明细
        lines = []
        for e in evaluations:
            direction_text = "增加收入" if e.direction == "income" else "增加成本"
            lines.append(
                f"规则：{e.rule_name}\n"
                f"场景：{scenario}\n"
                f"条件：{e.condition_field} {e.compare_op} {e.condition_value}\n"
                f"方向：{direction_text}\n"
                f"原币金额：{e.amount_original} {e.currency}\n"
                f"换算 RMB：¥{e.amount_rmb:.2f}"
            )
        label.setToolTip("\n\n".join(lines))

    # ------------------------------------------------------------------
    # SHEIN 核价比较
    # ------------------------------------------------------------------

    def _update_shein_comparison(self, na) -> None:
        if not self.lbl_conclusion:
            return
        shein_usd = self._shein_quote_usd
        na_price_usd = na.sale_price_usd if na else 0.0

        if shein_usd <= 0:
            # 核价为空：不提醒
            self.lbl_conclusion.setText("")
            self.lbl_conclusion.setStyleSheet("")
            if self.txt_shein_usd:
                self.txt_shein_usd.setStyleSheet("")
            return

        if na_price_usd <= 0:
            self.lbl_conclusion.setText("")
            return

        if na_price_usd <= shein_usd:
            self.lbl_conclusion.setText("未超过核价")
            self.lbl_conclusion.setStyleSheet(f"color:{_COLOR_NORMAL};")
            if self.txt_shein_usd:
                self.txt_shein_usd.setStyleSheet("")
        else:
            diff = na_price_usd - shein_usd
            pct = (diff / shein_usd * 100.0) if shein_usd > 0 else 0.0
            self.lbl_conclusion.setText(f"超过核价 ${diff:.2f}（{pct:.1f}%）")
            self.lbl_conclusion.setStyleSheet(f"color:#D32F2F;font-weight:600;")
            if self.txt_shein_usd:
                self.txt_shein_usd.setStyleSheet("border: 2px solid #D32F2F;")

    def _update_shein_comparison_from_values(self) -> None:
        """旧记录加载路径：用内部保存的无活动售价做核价比较，不触发重算。"""

        class _Snap:
            sale_price_usd = self._no_activity_price_usd

        self._update_shein_comparison(_Snap())

    # ------------------------------------------------------------------
    # 用户编辑处理（driver 切换）
    # ------------------------------------------------------------------

    def _on_shein_quote_changed(self, _value: float) -> None:
        """SHEIN 核价 USD 变化：不改变 driver，不退出快照，不重算利润/规则。

        只更新 SHEIN 核价 RMB 换算和与无活动售价的差额提醒。
        即使保存记录后汇率或规则已经变化，单独修改核价也不得
        间接改变利润结果。
        """
        if self._profit_updating:
            return
        # 不调用 _exit_snapshot_mode()，不调用 _refresh_all()
        # 只做冻结换算和差额提醒
        self._profit_updating = True
        try:
            shein_usd = self.txt_shein_usd.value() if self.txt_shein_usd else 0.0
            self._shein_quote_usd = shein_usd
            rate = self._exchange_rate
            self._set_spin(self.txt_shein_rmb, shein_usd * rate if rate > 0 else 0.0)
            self._update_shein_comparison_from_values()
        finally:
            self._profit_updating = False
        self.profitChanged.emit()

    def _on_calc_cost_changed(self, _value: float) -> None:
        """计算总成本 RMB 变化：用户手动修改成本。"""
        self._exit_snapshot_mode()
        # 用户手动成本优先于快照期间捕获的系统成本
        if self.txt_cost_rmb:
            self._calculation_total_cost_rmb = self.txt_cost_rmb.value()
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def _on_profit_rate_changed(self, _value: float) -> None:
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def _on_list_price_rate_changed(self, _value: float) -> None:
        """标价利率编辑：退出快照模式，标价利率成为当前 driver。"""
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_NO_ACTIVITY_PROFIT_RATE
        self._refresh_all()

    def _on_na_price_changed(self, _value: float) -> None:
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        if self.txt_na_price_usd:
            self._no_activity_price_usd = self.txt_na_price_usd.value()
        self._refresh_all()

    def _on_na_profit_changed(self, _value: float) -> None:
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
        self._refresh_all()

    def _on_reserve_changed(self, _value: float) -> None:
        """活动预留变化：保持当前活动后利润率目标，重算其余依赖值。"""
        if self.spin_reserve:
            self._reserve_percent = self.spin_reserve.value()
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def _on_act_profit_changed(self, _value: float) -> None:
        self._exit_snapshot_mode()
        self._profit_driver = DRIVER_ACTIVITY_PROFIT
        self._refresh_all()

    def _exit_snapshot_mode(self) -> None:
        """用户主动编辑利润区字段：退出快照显示模式，之后属当前推算。

        恢复快照期间捕获的当前设置（汇率/规则/选中规则），使后续重算使用
        当前设置，而不是继续使用保存时的历史快照值。

        计算总成本不在此恢复：它是上游状态，显示中的快照成本（或用户/
        上游随后显式设置的成本）保持不变，绝不因下游利润字段编辑而
        被内部捕获的值静默替换。

        旧记录兼容状态被退出后，标记 _legacy_exited=True，后续保存可
        使用双场景 schema（不再保持 legacy_compatible=True）。
        """
        if not self._snapshot_display_mode:
            return
        self._snapshot_display_mode = False
        if self._snapshot_legacy:
            self._legacy_exited = True
        if self._live_exchange_rate is not None:
            self._exchange_rate = self._live_exchange_rate
        if self._live_rules is not None:
            self._rules = self._live_rules
            self._refresh_rule_combo()
        if self._live_selected_rule_id is not None:
            self._selected_rule_id = self._live_selected_rule_id
            self._refresh_rule_combo()
        self._live_exchange_rate = None
        self._live_rules = None
        self._live_selected_rule_id = None
        self._update_snapshot_status_label()

    def capture_current_settings(self, *, exchange_rate: float, rules, selected_rule_id: str = "") -> None:
        """打开记录前捕获当前设置状态（汇率/启用规则/选中规则），供退出快照模式时恢复。

        只捕获设置类状态；计算总成本是上游状态，不参与捕获/恢复。
        """
        self._live_exchange_rate = float(exchange_rate) if exchange_rate > 0 else None
        self._live_rules = tuple(rules)
        self._live_selected_rule_id = str(selected_rule_id or "")

    # ------------------------------------------------------------------
    # 快照状态提示（复用 lblProfitConclusion / tooltip）
    # ------------------------------------------------------------------

    # 状态文案常量
    _STATUS_HISTORY = "历史快照"
    _STATUS_LEGACY = "旧记录兼容数据"
    _STATUS_CURRENT = "当前推算（非历史快照）"

    def _current_snapshot_status(self) -> str:
        """返回当前快照状态文案。"""
        if self._snapshot_loaded and self._snapshot_legacy and not self._legacy_exited:
            return self._STATUS_LEGACY
        if self._snapshot_display_mode:
            return self._STATUS_HISTORY
        return self._STATUS_CURRENT

    def _update_snapshot_status_label(self) -> None:
        """更新利润区状态提示（复用 lblProfitConclusion tooltip）。

        不修改冻结 .ui 布局，不新增占用高度的控件。
        将当前快照状态写入 lblProfitConclusion 的 tooltip，用户可
        从界面 tooltip 明确区分三种状态。

        写入前删除 tooltip 中已有的所有"[利润区状态] ..."行，
        保留其他核价差额或说明内容，最终只追加一条当前最新状态。
        如果 lblProfitConclusion 当前有差额提醒文本（如"超过核价"），
        保留提醒文本不覆盖。如果无提醒文本，直接显示状态文案。
        """
        if not self.lbl_conclusion:
            return
        status = self._current_snapshot_status()
        existing_text = self.lbl_conclusion.text()
        existing_tip = self.lbl_conclusion.toolTip()
        # 清理 tooltip 中已有的 [利润区状态] 行，保留其他内容
        tip_parts = []
        if existing_tip and existing_tip.strip():
            for line in existing_tip.strip().split("\n"):
                stripped = line.strip()
                if stripped.startswith("[利润区状态]"):
                    continue  # 删除旧状态行
                if stripped:
                    tip_parts.append(stripped)
        tip_parts.append(f"[利润区状态] {status}")
        self.lbl_conclusion.setToolTip("\n".join(tip_parts))
        # 如果无差额提醒文本，显示状态文案
        if not existing_text or not existing_text.strip() or existing_text.strip() in (
            self._STATUS_HISTORY, self._STATUS_LEGACY, self._STATUS_CURRENT
        ):
            if status == self._STATUS_LEGACY:
                self.lbl_conclusion.setText(self._STATUS_LEGACY)
                self.lbl_conclusion.setStyleSheet(f"color:{_COLOR_NORMAL};")
            elif status == self._STATUS_HISTORY:
                self.lbl_conclusion.setText(self._STATUS_HISTORY)
                self.lbl_conclusion.setStyleSheet(f"color:{_COLOR_NORMAL};")
            else:
                self.lbl_conclusion.setText("")
                self.lbl_conclusion.setStyleSheet("")

    # ------------------------------------------------------------------
    # 数据导出（供记录保存使用）
    # ------------------------------------------------------------------

    def export_profit_scenarios(self) -> dict[str, Any]:
        """导出当前利润区状态为 profit_scenarios 字段。

        除双场景数值外，还写入保存时快照字段：
        - ``exchange_rate``：保存时汇率；
        - ``applied_rule_ids``：实际应用的规则 ID 集合；
        - ``applied_rules``：完整应用规则快照（含未命中规则）；
        - ``selected_rule_id``：当前规则下拉选择；
        - ``legacy_compatible``：新记录恒为 False。

        旧记录兼容状态未被用户明确操作退出时，再次保存仍保持
        legacy_compatible=True，活动场景为空，不伪造活动历史数据。
        """
        from profit_accounting_26.application.profit_scenario_codec import (
            build_profit_scenarios,
            rules_to_snapshot,
        )

        cost = self._calculation_total_cost_rmb
        rate = self._exchange_rate
        reserve = self._reserve_percent
        na_price = self._no_activity_price_usd
        shein = self._shein_quote_usd
        active_rules = self._active_rules()

        # 旧记录兼容状态未被明确操作退出时，原样输出加载时的历史值，
        # 不重新推导售价/利润/利润率
        if self._snapshot_loaded and self._snapshot_legacy and not self._legacy_exited:
            snap = self._legacy_snapshot or {}
            return build_profit_scenarios(
                driver=self._profit_driver,
                calculation_total_cost_rmb=snap.get("calculation_total_cost_rmb", cost),
                shein_quote_usd=shein,
                reserve_percent=reserve,
                no_activity_price_usd=snap.get("no_activity_sale_price_usd", na_price),
                no_activity_price_rmb=snap.get("no_activity_sale_price_rmb", 0.0),
                no_activity_profit_rmb=snap.get("no_activity_profit_rmb", 0.0),
                no_activity_profit_usd=snap.get("no_activity_profit_usd", 0.0),
                no_activity_rule_status=snap.get("rule_status", {}),
                activity_price_usd=0.0,
                activity_price_rmb=0.0,
                activity_profit_rmb=0.0,
                activity_profit_usd=0.0,
                activity_profit_rate_on_cost=snap.get("profit_rate_on_cost"),
                activity_rule_status={},
                exchange_rate=snap.get("exchange_rate", rate),
                applied_rule_ids=[],
                applied_rules=[],
                selected_rule_id=self._selected_rule_id,
                legacy_compatible=True,
            )

        if na_price > 0 and rate > 0:
            result = calculate_dual_profit(
                no_activity_price_usd=na_price,
                reserve_percent=reserve,
                total_cost_rmb=cost,
                exchange_rate=rate,
                rules=active_rules,
            )
            na = result.no_activity
            act = result.activity
            profit_rate = result.profit_rate
        else:
            na = None
            act = None
            profit_rate = None

        return build_profit_scenarios(
            driver=self._profit_driver,
            calculation_total_cost_rmb=cost,
            shein_quote_usd=shein,
            reserve_percent=reserve,
            no_activity_price_usd=na_price,
            no_activity_price_rmb=na.sale_price_rmb if na else 0.0,
            no_activity_profit_rmb=na.profit_rmb if na else 0.0,
            no_activity_profit_usd=na.profit_usd if na else 0.0,
            no_activity_rule_status=self._export_rule_status(na, "no_activity"),
            activity_price_usd=act.sale_price_usd if act else 0.0,
            activity_price_rmb=act.sale_price_rmb if act else 0.0,
            activity_profit_rmb=act.profit_rmb if act else 0.0,
            activity_profit_usd=act.profit_usd if act else 0.0,
            activity_profit_rate_on_cost=profit_rate,
            activity_rule_status=self._export_rule_status(act, "activity"),
            exchange_rate=rate,
            applied_rule_ids=[rule.id for rule in active_rules],
            applied_rules=rules_to_snapshot(self._rules),
            selected_rule_id=self._selected_rule_id,
            legacy_compatible=False,
        )

    @staticmethod
    def _export_rule_status(scenario_result, scenario: str) -> dict[str, Any]:
        if scenario_result is None:
            return {}
        evaluations = [e for e in scenario_result.rule_evaluations if e.scenario == scenario and e.matched]
        return {
            "matched_count": len(evaluations),
            "total_income_rmb": sum(e.amount_rmb for e in evaluations if e.direction == "income"),
            "total_cost_rmb": sum(e.amount_rmb for e in evaluations if e.direction == "cost"),
            "rules": [
                {
                    "id": e.rule_id,
                    "name": e.rule_name,
                    "direction": e.direction,
                    "amount_rmb": e.amount_rmb,
                    "amount_original": e.amount_original,
                    "currency": e.currency,
                }
                for e in evaluations
            ],
        }

    # ------------------------------------------------------------------
    # 记录加载（向后兼容）
    # ------------------------------------------------------------------

    def load_from_record(self, record: dict[str, Any]) -> None:
        """从记录加载利润区数据，支持旧记录兼容。

        新记录：使用保存时汇率与完整规则快照，界面结果与保存时完全一致，
        不按当前设置静默重新计算。
        旧记录：只恢复无活动历史字段，活动场景保持为空，不伪造活动历史。
        """
        from profit_accounting_26.application.profit_scenario_codec import (
            extract_profit_scenarios,
            is_legacy_record,
            rules_from_snapshot,
        )

        scenarios = extract_profit_scenarios(record)
        if scenarios is None:
            # 无利润数据：清空
            self._snapshot_loaded = False
            self._snapshot_legacy = False
            self._snapshot_display_mode = False
            self._no_activity_price_usd = 0.0
            self._reserve_percent = 0.0
            self._calculation_total_cost_rmb = 0.0
            self._shein_quote_usd = 0.0
            self._profit_driver = DRIVER_NO_ACTIVITY_PRICE
            self._refresh_all()
            return

        self._snapshot_loaded = True
        self._snapshot_legacy = is_legacy_record(scenarios)
        self._legacy_exited = False

        self._calculation_total_cost_rmb = float(scenarios.get("calculation_total_cost_rmb", 0) or 0)
        self._shein_quote_usd = float(scenarios.get("shein_quote_usd", 0) or 0)
        self._reserve_percent = float(scenarios.get("reserve_percent", 0) or 0)
        driver = scenarios.get("driver", DRIVER_NO_ACTIVITY_PRICE)
        if driver in _VALID_DRIVERS:
            self._profit_driver = driver

        # 保存时汇率与完整规则快照：重开用它们，不按当前设置静默重算
        saved_rate = float(scenarios.get("exchange_rate", 0) or 0)
        if saved_rate > 0:
            self._exchange_rate = saved_rate
        snapshot_rules = rules_from_snapshot(scenarios.get("applied_rules"))
        if snapshot_rules:
            self._rules = snapshot_rules
            saved_rule_id = str(scenarios.get("selected_rule_id") or "")
            self._selected_rule_id = saved_rule_id
            self._refresh_rule_combo()

        na = scenarios.get("no_activity", {})
        act = scenarios.get("activity", {})
        self._no_activity_price_usd = float(na.get("sale_price_usd", 0) or 0)

        legacy = self._snapshot_legacy

        # 旧记录：保存原始利润快照，export 时原样输出不重算
        if legacy:
            self._legacy_snapshot = {
                "no_activity_sale_price_usd": float(na.get("sale_price_usd", 0) or 0),
                "no_activity_sale_price_rmb": float(na.get("sale_price_rmb", 0) or 0),
                "no_activity_profit_rmb": float(na.get("profit_rmb", 0) or 0),
                "no_activity_profit_usd": float(na.get("profit_usd", 0) or 0),
                "profit_rate_on_cost": float(act.get("profit_rate_on_cost", 0) or 0) if act.get("profit_rate_on_cost") is not None else None,
                "calculation_total_cost_rmb": self._calculation_total_cost_rmb,
                "exchange_rate": self._exchange_rate if self._exchange_rate > 0 else saved_rate,
                "rule_status": na.get("rule_status", {}),
            }
        else:
            self._legacy_snapshot = None

        # 先置位快照显示模式，再程序化填充控件。
        # 填充期间必须阻断 valueChanged，否则 handler 会触发 _exit_snapshot_mode
        # 把刚置位的快照模式清除，导致加载后仍按当前设置静默重算。
        self._snapshot_display_mode = True
        self._profit_updating = True
        editable_widgets = [
            self.txt_shein_usd,
            self.txt_cost_rmb,
            self.spin_profit_rate,
            self.txt_list_price_rate,
            self.txt_na_price_usd,
            self.txt_na_profit_rmb,
            self.spin_reserve,
            self.txt_act_profit_rmb,
        ]
        blockers = [QSignalBlocker(w) for w in editable_widgets if w]
        try:
            if self.txt_shein_usd:
                self.txt_shein_usd.setValue(self._shein_quote_usd)
            if self.spin_reserve:
                self.spin_reserve.setValue(self._reserve_percent)
            if self.txt_na_price_usd:
                self.txt_na_price_usd.setValue(self._no_activity_price_usd)
            if self.txt_cost_rmb:
                self.txt_cost_rmb.setValue(self._calculation_total_cost_rmb)
            if self.txt_na_profit_rmb:
                self.txt_na_profit_rmb.setValue(float(na.get("profit_rmb", 0) or 0))
            # 冻结换算字段同样恢复为保存时数值（界面结果与保存时完全一致）
            if self.txt_na_price_rmb:
                self.txt_na_price_rmb.setValue(float(na.get("sale_price_rmb", 0) or 0))
            if self.txt_na_profit_usd:
                self.txt_na_profit_usd.setValue(float(na.get("profit_usd", 0) or 0))
            if legacy:
                # 旧记录：活动场景保持为空，不伪造活动历史
                for widget in (
                    self.txt_act_price_usd,
                    self.txt_act_price_rmb,
                    self.txt_act_profit_rmb,
                    self.txt_act_profit_usd,
                ):
                    if widget:
                        widget.setValue(0.0)
                if self.spin_profit_rate:
                    self.spin_profit_rate.setValue(0.0)
                if self.lbl_act_status:
                    self.lbl_act_status.setText("")
                    self.lbl_act_status.setToolTip("")
            else:
                if self.txt_act_price_usd:
                    self.txt_act_price_usd.setValue(float(act.get("sale_price_usd", 0) or 0))
                if self.txt_act_price_rmb:
                    self.txt_act_price_rmb.setValue(float(act.get("sale_price_rmb", 0) or 0))
                if self.txt_act_profit_rmb:
                    self.txt_act_profit_rmb.setValue(float(act.get("profit_rmb", 0) or 0))
                if self.txt_act_profit_usd:
                    self.txt_act_profit_usd.setValue(float(act.get("profit_usd", 0) or 0))
                if self.spin_profit_rate:
                    rate_val = act.get("profit_rate_on_cost")
                    self.spin_profit_rate.setValue(float(rate_val) * 100 if rate_val is not None else 0.0)
        finally:
            del blockers
            self._profit_updating = False

        if legacy:
            # 旧记录：只恢复无活动历史字段，活动场景保持为空，
            # 不伪造活动场景历史；后续自动刷新仅做冻结换算显示。
            if self.lbl_na_status:
                self.lbl_na_status.setText("无规则")
                self.lbl_na_status.setStyleSheet(f"color:{_COLOR_NORMAL};")
                self.lbl_na_status.setToolTip("")
        else:
            # 新记录：从保存快照恢复两规则状态标签（与保存时一致）
            self._restore_rule_status_labels(na.get("rule_status"), self.lbl_na_status)
            self._restore_rule_status_labels(act.get("rule_status"), self.lbl_act_status)

        self._snapshot_display_mode = True
        self._do_display_only_refresh()
        self._update_snapshot_status_label()
        self.profitChanged.emit()

    def _restore_rule_status_labels(self, rule_status: dict[str, Any] | None, label: QLabel | None) -> None:
        """从保存的规则状态快照恢复状态标签文本与 tooltip。"""
        if label is None:
            return
        status = rule_status or {}
        matched = int(status.get("matched_count", 0) or 0)
        if matched <= 0:
            label.setText("无规则" if not status else "未触发")
            label.setStyleSheet(f"color:{_COLOR_NORMAL};")
            label.setToolTip("")
            return
        income = float(status.get("total_income_rmb", 0) or 0)
        cost_adj = float(status.get("total_cost_rmb", 0) or 0)
        net = income - cost_adj
        if net >= 0:
            label.setText(f"已触发 +¥{net:.2f}")
            label.setStyleSheet(f"color:{_COLOR_TRIGGERED_INCOME};font-weight:600;")
        else:
            label.setText(f"已调整 ¥{net:.2f}")
            label.setStyleSheet(f"color:{_COLOR_TRIGGERED_COST};font-weight:600;")
        lines = []
        for rule in status.get("rules", []):
            if not isinstance(rule, dict):
                continue
            direction_text = "增加收入" if rule.get("direction") == "income" else "增加成本"
            amount_rmb = float(rule.get("amount_rmb", 0) or 0)
            lines.append(
                f"规则：{rule.get('name', '')}\n"
                f"方向：{direction_text}\n"
                f"原币金额：{rule.get('amount_original', 0)} {rule.get('currency', '')}\n"
                f"换算 RMB：¥{amount_rmb:.2f}"
            )
        label.setToolTip("\n\n".join(lines))
