"""主软件三项利润字段的“明确保存后沿用”默认值机制（本轮唯一主软件业务改动）。

范围严格限定在以下 3 个现有 objectName 所代表的输入项：
- ``spinPromotionReserve``（活动预留）
- ``txtListPriceProfitRate``（标价利率）
- ``spinProfitRate``（活动后利润率）

统一行为：
1. 只有用户执行主软件现有“明确保存”动作且保存成功后，才把这 3 项当时的
   值记为以后默认值（``capture_profit_defaults``）；
2. 仅编辑但没有保存，不改变默认值；
3. 下次打开软件（``apply_profit_defaults`` 于启动/清空后调用）恢复用户
   上一次明确保存的这 3 项；
4. 历史上从未保存过 → 沿用当前既有初始默认（活动预留 15%、活动后利润率 25%；
   标价利率保持现有派生语义，不强设）；
5. UU测算 启动与“清空”读取同一套默认值，但 Quick 没有保存商品动作，
   绝不允许把 Quick 中的临时修改写回默认值（Quick 不调用 capture）。

保存进现有 SettingsService / settings 数据（向后兼容新键），
不新增数据库表、不做 migration、不改变历史记录结构。
"""

from __future__ import annotations

from typing import Any

from profit_accounting_26.ui.binders.calculation_binder import (
    DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT,
    DEFAULT_RESERVE_PERCENT,
)

RESERVE_DEFAULT_KEY = "default_profit_reserve_percent"
ACTIVITY_RATE_DEFAULT_KEY = "default_activity_profit_rate_percent"
LIST_PRICE_RATE_DEFAULT_KEY = "default_list_price_profit_rate_percent"

DEFAULT_KEYS = (RESERVE_DEFAULT_KEY, ACTIVITY_RATE_DEFAULT_KEY, LIST_PRICE_RATE_DEFAULT_KEY)


def capture_profit_defaults(settings: dict[str, Any], binder) -> None:
    """主软件明确保存成功后调用：把当时这 3 项的值记为以后默认值。"""
    settings[RESERVE_DEFAULT_KEY] = float(
        binder.spin_reserve.value()
        if binder.spin_reserve is not None
        else DEFAULT_RESERVE_PERCENT
    )
    settings[ACTIVITY_RATE_DEFAULT_KEY] = float(
        binder.spin_profit_rate.value()
        if binder.spin_profit_rate is not None
        else DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT
    )
    settings[LIST_PRICE_RATE_DEFAULT_KEY] = float(
        binder.txt_list_price_rate.value()
        if binder.txt_list_price_rate is not None
        else 0.0
    )


def apply_profit_defaults(settings: dict[str, Any], binder) -> None:
    """启动 / 清空后调用：恢复用户上一次明确保存的默认值。

    - 键不存在（从未保存）→ 沿用现有初始默认：活动预留 15%、活动后利润率 25%；
      标价利率保持现有派生语义（由 Binder 自行计算/清零），不强设；
    - 设置顺序：先标价利率、再活动预留、最后活动后利润率。共享 Binder 在
      ``txtListPriceProfitRate`` valueChanged 时会把内部 driver 改写为
      “标价利率”，随后由活动预留/活动后利润率的 handler 把 driver 改回
      “活动后利润率”，保证清空/启动后状态与主软件既有新建语义一致。
    """
    if binder.txt_list_price_rate is not None:
        value = settings.get(LIST_PRICE_RATE_DEFAULT_KEY)
        if value is not None:
            binder.txt_list_price_rate.setValue(float(value))
    if binder.spin_reserve is not None:
        value = settings.get(RESERVE_DEFAULT_KEY)
        binder.spin_reserve.setValue(
            float(value) if value is not None else DEFAULT_RESERVE_PERCENT
        )
    if binder.spin_profit_rate is not None:
        value = settings.get(ACTIVITY_RATE_DEFAULT_KEY)
        binder.spin_profit_rate.setValue(
            float(value) if value is not None else DEFAULT_ACTIVITY_PROFIT_RATE_PERCENT
        )
