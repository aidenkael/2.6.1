from __future__ import annotations

from collections.abc import Iterable

from profit_accounting_26.domain.models import Forwarder, PackageSpec
from profit_accounting_26.domain.rules import AdjustmentRule
from profit_accounting_26.engines.logistics import calculate_logistics, calculate_system_cost
from profit_accounting_26.engines.profit import (
    calculate_profit,
    sale_price_for_target_profit,
    sale_price_for_target_rate,
)


class CalculationService:
    def quote(
        self,
        *,
        package: PackageSpec,
        forwarder: Forwarder,
        product_cost_rmb: float,
        domestic_shipping_rmb: float,
        tail_fee_rmb: float,
        sale_price_usd: float,
        exchange_rate: float,
        reserve_rate: float = 0.0,
        rules: Iterable[AdjustmentRule] = (),
        adopted_total_cost_rmb: float | None = None,
    ) -> dict[str, object]:
        logistics = calculate_logistics(package, forwarder, tail_fee_rmb=tail_fee_rmb)
        system_cost = calculate_system_cost(
            product_cost_rmb=product_cost_rmb,
            domestic_shipping_rmb=domestic_shipping_rmb,
            logistics_total_rmb=logistics.total_logistics_rmb,
        )
        calculation_cost = system_cost if adopted_total_cost_rmb is None else adopted_total_cost_rmb
        profit = calculate_profit(
            total_cost_rmb=calculation_cost,
            sale_price_usd=sale_price_usd,
            exchange_rate=exchange_rate,
            reserve_rate=reserve_rate,
            rules=rules,
        )
        return {
            "logistics": logistics,
            "system_cost_rmb": system_cost,
            "calculation_cost_rmb": calculation_cost,
            "profit": profit,
        }

    def quote_all_forwarders(
        self,
        *,
        package: PackageSpec,
        forwarders: Iterable[Forwarder],
        tail_fee_rmb: float,
    ) -> dict[str, object]:
        return {
            forwarder.id: calculate_logistics(package, forwarder, tail_fee_rmb=tail_fee_rmb)
            for forwarder in forwarders
            if forwarder.enabled and not forwarder.archived
        }

    @staticmethod
    def price_for_target_profit(
        *,
        total_cost_rmb: float,
        target_profit_rmb: float,
        exchange_rate: float,
        reserve_rate: float,
        net_adjustment_rmb: float = 0.0,
        rules: Iterable[AdjustmentRule] = (),
    ) -> float:
        return sale_price_for_target_profit(
            total_cost_rmb=total_cost_rmb,
            target_profit_rmb=target_profit_rmb,
            exchange_rate=exchange_rate,
            reserve_rate=reserve_rate,
            net_adjustment_rmb=net_adjustment_rmb,
            rules=rules,
        )

    @staticmethod
    def price_for_target_rate(
        *,
        total_cost_rmb: float,
        target_rate_on_cost: float,
        exchange_rate: float,
        reserve_rate: float,
        net_adjustment_rmb: float = 0.0,
        rules: Iterable[AdjustmentRule] = (),
    ) -> float:
        return sale_price_for_target_rate(
            total_cost_rmb=total_cost_rmb,
            target_rate_on_cost=target_rate_on_cost,
            exchange_rate=exchange_rate,
            reserve_rate=reserve_rate,
            net_adjustment_rmb=net_adjustment_rmb,
            rules=rules,
        )
