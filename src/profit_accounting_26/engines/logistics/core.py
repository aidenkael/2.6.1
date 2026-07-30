from __future__ import annotations

from profit_accounting_26.domain.models import Forwarder, LogisticsQuote, PackageSpec


def calculate_logistics(
    package: PackageSpec,
    forwarder: Forwarder,
    *,
    tail_fee_rmb: float,
) -> LogisticsQuote:
    package.validate()
    forwarder.validate()
    if tail_fee_rmb < 0:
        raise ValueError("尾程费用不能为负数")

    actual_weight_kg = package.weight_g / 1000.0
    volume_weight_kg = (
        package.length_cm * package.width_cm * package.height_cm / forwarder.volume_divisor
    )
    chargeable_weight_kg = max(actual_weight_kg, volume_weight_kg)
    weight_fee_rmb = chargeable_weight_kg * forwarder.rate_rmb_per_kg
    total = weight_fee_rmb + forwarder.fixed_fee_rmb + tail_fee_rmb
    return LogisticsQuote(
        forwarder_id=forwarder.id,
        actual_weight_kg=actual_weight_kg,
        volume_weight_kg=volume_weight_kg,
        chargeable_weight_kg=chargeable_weight_kg,
        weight_fee_rmb=weight_fee_rmb,
        fixed_fee_rmb=forwarder.fixed_fee_rmb,
        tail_fee_rmb=tail_fee_rmb,
        total_logistics_rmb=total,
    )


def calculate_system_cost(
    *,
    product_cost_rmb: float,
    domestic_shipping_rmb: float,
    logistics_total_rmb: float,
) -> float:
    values = (product_cost_rmb, domestic_shipping_rmb, logistics_total_rmb)
    if any(value < 0 for value in values):
        raise ValueError("成本项不能为负数")
    return sum(values)
