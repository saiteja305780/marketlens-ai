"""Pure price-history maths. No database, no network: easy to test and impossible to
accidentally mix up with data fetching."""
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from app.schemas.api import HistoryStats, ObservationOut

CENT = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_history_stats(observations: Sequence[ObservationOut]) -> tuple[HistoryStats | None, list[str]]:
    """Return (stats, warnings). Stats are None when a trustworthy number can't be produced.
    Rules: only observations with a price count; different currencies are never combined;
    one data point gives no trend."""
    priced = sorted((o for o in observations if o.price is not None), key=lambda o: o.observed_at)
    warnings: list[str] = []

    if not priced:
        return None, ["no priced observations in this range"]

    currencies = {o.currency for o in priced}
    if len(currencies) > 1:
        return None, [f"observations use several currencies ({', '.join(sorted(str(c) for c in currencies))}); "
                      "no cross-currency calculations are made"]

    first, latest = priced[0], priced[-1]
    prices = [o.price for o in priced]
    change = pct = None
    if len(priced) == 1:
        warnings.append("only one priced observation; no trend can be calculated")
    else:
        change = _q(latest.price - first.price)
        pct = _q((latest.price - first.price) / first.price * 100)

    return HistoryStats(
        currency=str(first.currency), observation_count=len(priced),
        first_observed_at=first.observed_at, latest_observed_at=latest.observed_at,
        first_price=first.price, latest_price=latest.price,
        lowest_price=min(prices), highest_price=max(prices),
        absolute_change=change, percent_change=pct,
    ), warnings
