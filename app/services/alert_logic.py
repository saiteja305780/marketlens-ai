"""Pure alert decision logic: no database, no I/O. One function, easy to test.

A rule fires only when its condition goes from false to true. Missing, zero, unknown or
wrong-currency data tells us nothing, so it never fires and never changes the stored state."""
from decimal import Decimal

PRICE_BELOW = "price_below"
BACK_IN_STOCK = "back_in_stock"
RULE_TYPES = (PRICE_BELOW, BACK_IN_STOCK)


def _condition(rule_type: str, threshold: Decimal | None, rule_currency: str | None,
               price: Decimal | None, currency: str | None, availability: str | None) -> bool | None:
    """True/False when the data is usable, None when it is not."""
    if rule_type == PRICE_BELOW:
        if threshold is None or rule_currency is None:
            return None
        if price is None or price <= 0 or currency != rule_currency:
            return None
        return price <= threshold
    if rule_type == BACK_IN_STOCK:
        if availability == "in_stock":
            return True
        if availability == "out_of_stock":
            return False
        return None
    raise ValueError(f"unknown rule type {rule_type!r}")


def evaluate(rule_type: str, threshold: Decimal | None, rule_currency: str | None,
             prev_met: bool | None, price: Decimal | None, currency: str | None,
             availability: str | None) -> tuple[bool | None, bool]:
    """Returns (new_state, fire). The first evaluation (prev_met None) records state without firing."""
    now_met = _condition(rule_type, threshold, rule_currency, price, currency, availability)
    if now_met is None:
        return prev_met, False
    return now_met, (prev_met is False and now_met is True)