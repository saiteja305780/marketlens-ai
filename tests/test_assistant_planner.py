from app.assistant.planner import Clarify, Plan, plan_question


def plan(q, sources=()):
    return plan_question(q, list(sources))


def test_search_with_source_price_and_stock():
    p = plan("noise earbuds under 1500 in stock", ["noise"])
    assert isinstance(p, Plan) and p.tool == "search_listings"
    assert p.args == {"text": "earbuds", "source": "noise", "availability": "in_stock", "max_price": "1500"}
    assert p.needs_currency is True


def test_cheapest_sorts_by_price():
    p = plan("cheapest noise earbuds", ["noise"])
    assert p.args == {"text": "earbuds", "source": "noise", "sort": "price", "order": "asc"}
    assert p.needs_currency is True


def test_currency_symbol_words_are_understood():
    p = plan("watches under rs. 3000")
    assert p.args == {"text": "watches", "max_price": "3000", "currency": "INR"}
    assert p.needs_currency is False


def test_between_with_k_suffix():
    p = plan("between 1k and 2k")
    assert p.args == {"min_price": "1000", "max_price": "2000"}


def test_top_n_sets_limit():
    p = plan("top 3 cheapest earbuds")
    assert p.args == {"text": "earbuds", "sort": "price", "order": "asc", "limit": 3}


def test_out_of_stock():
    p = plan("out of stock watches")
    assert p.args == {"text": "watches", "availability": "out_of_stock"}


def test_compare_ids():
    p = plan("compare 12 and 15")
    assert p.tool == "compare_listings" and p.args == {"listing_ids": [12, 15]}


def test_compare_needs_two_ids():
    assert isinstance(plan("compare 12"), Clarify)


def test_price_history_of_listing():
    p = plan("price history of listing 12")
    assert p.tool == "get_price_history" and p.args == {"listing_id": 12}


def test_history_without_id_asks_which():
    assert isinstance(plan("price history"), Clarify)


def test_alerts_default_and_all():
    assert plan("alerts").args == {"unread_only": True}
    assert plan("show all alerts").args == {"unread_only": False}


def test_single_listing():
    p = plan("listing 12")
    assert p.tool == "get_listing" and p.args == {"listing_id": 12}


def test_nothing_to_search_gives_help():
    c = plan("show me")
    assert isinstance(c, Clarify) and "I can search" in c.message
