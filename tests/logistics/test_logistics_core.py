import pytest

from profit_accounting_26.domain.models import Forwarder, PackageSpec
from profit_accounting_26.engines.logistics import calculate_logistics, calculate_system_cost


def test_actual_weight_is_chargeable_when_larger():
    package = PackageSpec(10, 10, 10, 500)
    forwarder = Forwarder("sz", "深圳", 80, 10, 8000)
    quote = calculate_logistics(package, forwarder, tail_fee_rmb=40)
    assert quote.volume_weight_kg == pytest.approx(0.125)
    assert quote.chargeable_weight_kg == pytest.approx(0.5)
    assert quote.weight_fee_rmb == pytest.approx(40)
    assert quote.total_logistics_rmb == pytest.approx(90)


def test_volume_weight_is_chargeable_when_larger():
    package = PackageSpec(40, 30, 20, 200)
    forwarder = Forwarder("yw", "义乌", 100, 6, 8000)
    quote = calculate_logistics(package, forwarder, tail_fee_rmb=40)
    assert quote.volume_weight_kg == pytest.approx(3)
    assert quote.total_logistics_rmb == pytest.approx(346)


def test_system_cost_has_all_components():
    assert calculate_system_cost(
        product_cost_rmb=15, domestic_shipping_rmb=5, logistics_total_rmb=90
    ) == 110


def test_dynamic_forwarder_is_not_limited_to_defaults():
    forwarder = Forwarder("custom", "第三家货代", 73, 8, 7000)
    quote = calculate_logistics(PackageSpec(10, 10, 10, 100), forwarder, tail_fee_rmb=35)
    assert quote.forwarder_id == "custom"
