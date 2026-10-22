from decimal import Decimal as D

from app.services.alert_logic import BACK_IN_STOCK, PRICE_BELOW, evaluate

T = D("2000")


def price_rule(prev, price, currency="INR"):
    return evaluate(PRICE_BELOW, T, "INR", prev, None if price is None else D(price), currency, "in_stock")


def test_first_evaluation_records_state_without_firing():
    assert price_rule(None, "1500") == (True, False)
    assert price_rule(None, "2500") == (False, False)


def test_fires_on_transition_to_true():
    assert price_rule(False, "1999.00") == (True, True)


def test_threshold_is_inclusive():
    assert price_rule(False, "2000") == (True, True)


def test_does_not_repeat_while_condition_stays_true():
    assert price_rule(True, "1500") == (True, False)


def test_fires_again_after_leaving_and_returning():
    state, fired = price_rule(True, "2500")
    assert (state, fired) == (False, False)
    assert price_rule(state, "1500") == (True, True)


def test_missing_price_keeps_state_and_never_fires():
    assert price_rule(False, None) == (False, False)
    assert price_rule(True, None) == (True, False)


def test_zero_price_is_ignored():
    assert price_rule(False, "0") == (False, False)


def test_wrong_currency_is_ignored():
    assert price_rule(False, "1500", currency="USD") == (False, False)


def test_back_in_stock_transitions():
    assert evaluate(BACK_IN_STOCK, None, None, False, None, None, "in_stock") == (True, True)
    assert evaluate(BACK_IN_STOCK, None, None, True, None, None, "in_stock") == (True, False)
    assert evaluate(BACK_IN_STOCK, None, None, True, None, None, "out_of_stock") == (False, False)


def test_unknown_availability_is_ignored():
    assert evaluate(BACK_IN_STOCK, None, None, False, None, None, "unknown") == (False, False)