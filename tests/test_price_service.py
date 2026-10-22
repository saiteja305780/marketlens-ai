from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.schemas.api import ObservationOut
from app.services.price_service import compute_history_stats

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def obs(day, price, currency="INR", availability="in_stock"):
    return ObservationOut(observed_at=T0 + timedelta(days=day),
                          price=Decimal(price) if price is not None else None,
                          currency=currency, availability=availability)


def test_basic_stats_and_percent_change():
    stats, warnings = compute_history_stats([obs(0, "100.00"), obs(1, "90.00"), obs(2, "120.00")])
    assert warnings == []
    assert (stats.first_price, stats.latest_price) == (Decimal("100.00"), Decimal("120.00"))
    assert (stats.lowest_price, stats.highest_price) == (Decimal("90.00"), Decimal("120.00"))
    assert stats.absolute_change == Decimal("20.00") and stats.percent_change == Decimal("20.00")
    assert stats.observation_count == 3


def test_decrease_is_negative():
    stats, _ = compute_history_stats([obs(0, "200.00"), obs(1, "150.00")])
    assert stats.absolute_change == Decimal("-50.00") and stats.percent_change == Decimal("-25.00")


def test_input_order_does_not_matter():
    stats, _ = compute_history_stats([obs(2, "120.00"), obs(0, "100.00"), obs(1, "90.00")])
    assert stats.first_price == Decimal("100.00") and stats.latest_price == Decimal("120.00")


def test_single_observation_gives_no_trend():
    stats, warnings = compute_history_stats([obs(0, "100.00")])
    assert stats.absolute_change is None and stats.percent_change is None
    assert any("only one" in w for w in warnings)


def test_mixed_currencies_produce_no_numbers():
    stats, warnings = compute_history_stats([obs(0, "100.00", "INR"), obs(1, "2.00", "USD")])
    assert stats is None and "currencies" in warnings[0]


def test_unpriced_observations_are_ignored_not_treated_as_zero():
    stats, _ = compute_history_stats([obs(0, "100.00"), obs(1, None, availability="out_of_stock"), obs(2, "110.00")])
    assert stats.observation_count == 2 and stats.lowest_price == Decimal("100.00")


def test_no_priced_observations():
    stats, warnings = compute_history_stats([obs(0, None, availability="out_of_stock")])
    assert stats is None and warnings == ["no priced observations in this range"]


def test_rounding_to_two_decimals():
    stats, _ = compute_history_stats([obs(0, "300.00"), obs(1, "100.00")])
    assert stats.percent_change == Decimal("-66.67")
