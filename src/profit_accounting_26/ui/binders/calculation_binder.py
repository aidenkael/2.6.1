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
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QWidget,
)

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
DRIVER_ACTIVITY_PROFIT = "activity_profit"

_VALID_DRIVERS = (
    DRIVER_PROFIT_RATE,
    DRIVER_NO_ACTIVITY_PRICE,
    DRIVER_NO_ACTIVITY_PROFIT,
    DRIVER_ACTIVITY_PROFIT,
)

# 颜色常量
_COLOR_NORMAL = "#607089"
_COLOR_TRIGGERED_INCOME = "#168A58"  # 绿色：增加收入
_COLOR_TRIGGERED_COST = "#C77600"  # 警示色：增加成本


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
        self._profit_driver: str = DRIVER_NO_ACTIVITY_PRICE
        self._calculation_total_cost_rmb: float = 0.0
        self._exchange_rate: float = float(self.settings.get("exchange_rate_usd_to_rmb", 7.2))
        self._shein_quote_usd: float = 0.0
        self._reserve_percent: float = 0.0
        self._no_activity_price_usd: float = 0.0
        self._rules: tuple[AdjustmentRule, ...] = ()
        self._selected_rule_id: str = ""

        # 查找所有利润区控件
        self._find_widgets()
        self._sync_initial_values()
        self._setup_frozen_states()
        self._connect_signals()
        self._refresh_all()

    def _sync_initial_values(self) -> None:
        """从 .ui 控件读取初始值，同步到内部状态。

        .ui 文件可能设置了非零默认值（如 spinPromotionReserve=10），
        但 valueChanged 不会因 setValue(相同值) 触发，所以必须主动同步。
        """
        if self.spin_reserve:
            self._reserve_percent = self.spin_reserve.value()
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

    # ------------------------------------------------------------------
    # 冻结 / 可编辑状态
    # ------------------------------------------------------------------

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

    def set_rules(self, rules: tuple[AdjustmentRule, ...]) -> None:
        """设置利润规则列表（来自 SettingsService）。"""
        self._rules = rules
        self._refresh_rule_combo()
        self._refresh_all()

    def set_exchange_rate(self, rate: float) -> None:
        """汇率变化时更新冻结换算。"""
        if rate <= 0:
            return
        self._exchange_rate = rate
        self._refresh_all()

    def set_calculation_cost(self, cost_rmb: float) -> None:
        """上方成本变化时覆盖利润区计算总成本。"""
        self._calculation_total_cost_rmb = max(0.0, float(cost_rmb))
        self._refresh_all()

    def set_selected_rule_id(self, rule_id: str) -> None:
        self._selected_rule_id = rule_id
        self._refresh_rule_combo()

    @property
    def selected_rule_id(self) -> str:
        return self._selected_rule_id

    def set_shein_quote_usd(self, value: float) -> None:
        """外部（记录加载/清空）设置 SHEIN 核价 USD。"""
        if self.txt_shein_usd:
            self.txt_shein_usd.setValue(float(value))
        self._shein_quote_usd = float(value)

    def reset(self) -> None:
        """清空并新建时复位利润区（driver 回到无活动售价，全部数值归零）。"""
        self._profit_driver = DRIVER_NO_ACTIVITY_PRICE
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
                self.spin_profit_rate,
                self.txt_na_price_usd,
                self.txt_na_price_rmb,
                self.txt_na_profit_rmb,
                self.txt_na_profit_usd,
                self.txt_act_price_usd,
                self.txt_act_price_rmb,
                self.txt_act_profit_rmb,
                self.txt_act_profit_usd,
                self.spin_reserve,
            ):
                if widget:
                    widget.setValue(0.0)
            self._reserve_percent = 0.0
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
        """返回当前选中的规则（单选）。"""
        if not self.cmb_rule:
            return ()
        rule_id = self.cmb_rule.currentData()
        if not rule_id:
            return ()
        return tuple(r for r in self._rules if r.id == rule_id and r.enabled and not r.archived)

    def _on_rule_changed(self, _index: int) -> None:
        self._selected_rule_id = self.cmb_rule.currentData() if self.cmb_rule else ""
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
        self._profit_updating = True
        try:
            self._do_refresh()
        finally:
            self._profit_updating = False
        self.profitChanged.emit()

    def _do_refresh(self) -> None:
        driver = self._profit_driver
        rules = self._active_rules()
        cost = self._calculation_total_cost_rmb
        rate = self._exchange_rate
        reserve = self._reserve_percent
        na_price = self._no_activity_price_usd

        # 从 UI 读取当前 driver 的目标值
        if driver == DRIVER_PROFIT_RATE and self.spin_profit_rate:
            target_rate = self.spin_profit_rate.value() / 100.0
            if cost > 0:
                target_act_profit = cost * target_rate
                # 反推活动后售价，再反推无活动售价
                try:
                    act_price = sale_price_for_scenario_target_profit(
                        total_cost_rmb=cost,
                        target_profit_rmb=target_act_profit,
                        exchange_rate=rate,
                        rules=rules,
                        scenario="activity",
                    )
                    if reserve < 100:
                        na_price = act_price / (1 - reserve / 100.0)
                    else:
                        na_price = 0.0
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
        elif driver == DRIVER_ACTIVITY_PROFIT and self.txt_act_profit_rmb:
            target_act_profit = self.txt_act_profit_rmb.value()
            try:
                act_price = sale_price_for_scenario_target_profit(
                    total_cost_rmb=cost,
                    target_profit_rmb=target_act_profit,
                    exchange_rate=rate,
                    rules=rules,
                    scenario="activity",
                )
                if reserve < 100:
                    na_price = act_price / (1 - reserve / 100.0)
                else:
                    na_price = 0.0
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

        # 利润率（只在非 profit_rate driver 时更新，避免覆盖用户输入）
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

    # ------------------------------------------------------------------
    # 用户编辑处理（driver 切换）
    # ------------------------------------------------------------------

    def _on_shein_quote_changed(self, _value: float) -> None:
        """SHEIN 核价 USD 变化：不改变 driver，只刷新核价换算和比较。"""
        self._refresh_all()

    def _on_calc_cost_changed(self, _value: float) -> None:
        """计算总成本 RMB 变化：用户手动修改成本。"""
        if self.txt_cost_rmb:
            self._calculation_total_cost_rmb = self.txt_cost_rmb.value()
        self._refresh_all()

    def _on_profit_rate_changed(self, _value: float) -> None:
        self._profit_driver = DRIVER_PROFIT_RATE
        self._refresh_all()

    def _on_na_price_changed(self, _value: float) -> None:
        self._profit_driver = DRIVER_NO_ACTIVITY_PRICE
        if self.txt_na_price_usd:
            self._no_activity_price_usd = self.txt_na_price_usd.value()
        self._refresh_all()

    def _on_na_profit_changed(self, _value: float) -> None:
        self._profit_driver = DRIVER_NO_ACTIVITY_PROFIT
        self._refresh_all()

    def _on_reserve_changed(self, _value: float) -> None:
        """活动预留变化：无活动售价保持不变，活动后售价/利润/利润率重算。"""
        if self.spin_reserve:
            self._reserve_percent = self.spin_reserve.value()
        # driver 保持当前状态，不切换
        self._refresh_all()

    def _on_act_profit_changed(self, _value: float) -> None:
        self._profit_driver = DRIVER_ACTIVITY_PROFIT
        self._refresh_all()

    # ------------------------------------------------------------------
    # 数据导出（供记录保存使用）
    # ------------------------------------------------------------------

    def export_profit_scenarios(self) -> dict[str, Any]:
        """导出当前利润区状态为 profit_scenarios 字段。"""
        from profit_accounting_26.application.profit_scenario_codec import build_profit_scenarios

        cost = self._calculation_total_cost_rmb
        rate = self._exchange_rate
        reserve = self._reserve_percent
        na_price = self._no_activity_price_usd
        shein = self._shein_quote_usd

        if na_price > 0 and rate > 0:
            result = calculate_dual_profit(
                no_activity_price_usd=na_price,
                reserve_percent=reserve,
                total_cost_rmb=cost,
                exchange_rate=rate,
                rules=self._active_rules(),
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
        """从记录加载利润区数据，支持旧记录兼容。"""
        from profit_accounting_26.application.profit_scenario_codec import extract_profit_scenarios, is_legacy_record

        scenarios = extract_profit_scenarios(record)
        if scenarios is None:
            # 无利润数据：清空
            self._no_activity_price_usd = 0.0
            self._reserve_percent = 0.0
            self._calculation_total_cost_rmb = 0.0
            self._shein_quote_usd = 0.0
            self._profit_driver = DRIVER_NO_ACTIVITY_PRICE
            self._refresh_all()
            return

        self._calculation_total_cost_rmb = float(scenarios.get("calculation_total_cost_rmb", 0) or 0)
        self._shein_quote_usd = float(scenarios.get("shein_quote_usd", 0) or 0)
        self._reserve_percent = float(scenarios.get("reserve_percent", 0) or 0)
        driver = scenarios.get("driver", DRIVER_NO_ACTIVITY_PRICE)
        if driver in _VALID_DRIVERS:
            self._profit_driver = driver

        na = scenarios.get("no_activity", {})
        act = scenarios.get("activity", {})
        self._no_activity_price_usd = float(na.get("sale_price_usd", 0) or 0)

        # 更新 UI
        self._profit_updating = True
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
            if self.txt_act_profit_rmb:
                self.txt_act_profit_rmb.setValue(float(act.get("profit_rmb", 0) or 0))
            if self.spin_profit_rate:
                rate_val = act.get("profit_rate_on_cost")
                self.spin_profit_rate.setValue(float(rate_val) * 100 if rate_val is not None else 0.0)
        finally:
            self._profit_updating = False

        self._refresh_all()
