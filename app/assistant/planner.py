"""Turns a plain-English question into ONE tool call using fixed rules (no AI, no API key).
It only chooses a tool and its arguments; every number in an answer comes from the tools."""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

HELP = ("I can search listings (for example: 'noise earbuds under 1500 in stock' or 'cheapest watches'), "
        "show one listing ('listing 12'), give its price history ('price history of listing 12'), "
        "compare listings ('compare 12 and 15') and show alerts ('show alerts').")


@dataclass
class Plan:
    tool: str
    args: dict[str, Any]
    needs_currency: bool = False


@dataclass
class Clarify:
    message: str


_N = r"(\d[\d,]*(?:\.\d+)?)\s*(k)?"
_BETWEEN = re.compile(rf"\bbetween\s+{_N}\s+(?:and|to)\s+{_N}\b")
_MAX = re.compile(rf"\b(?:under|below|less than|up to|upto|within|at most|cheaper than|max)\s+{_N}\b")
_MIN = re.compile(rf"\b(?:over|above|more than|at least|min)\s+{_N}\b")
_DESC = re.compile(r"\b(?:most expensive|highest price|priciest|costliest)\b")
_ASC = re.compile(r"\b(?:cheapest|lowest price|least expensive)\b")
_OUT = re.compile(r"\b(?:out of stock|unavailable|sold out)\b")
_IN = re.compile(r"\b(?:in stock|available)\b")
_LISTING_1 = re.compile(r"(?:show|get|open)?\s*(?:me\s+)?(?:the\s+)?listing\s+#?(\d{1,9})\??")
_LISTING_2 = re.compile(r"(?:show|get|details?|info)\s+(?:of\s+|for\s+)?#?(\d{1,9})\??")
_STOP = {"show", "me", "find", "search", "list", "get", "give", "what", "which", "are", "is", "the", "a",
         "an", "of", "for", "in", "on", "with", "any", "all", "please", "products", "product", "listings",
         "listing", "items", "item", "do", "you", "have", "there", "i", "want", "need", "looking", "to",
         "and", "or", "than", "under", "below", "over", "above", "less", "more", "at", "from", "some",
         "can", "tell", "about"}


def _normalise(question: str) -> str:
    t = question.lower()
    t = t.replace("\u20b9", " inr ").replace("$", " usd ").replace("\u20ac", " eur ")
    t = re.sub(r"\brs\.?(?=\s|\d)", " inr ", t)
    return re.sub(r"\s+", " ", t).strip()


def _amount(number: str, k: str | None) -> str | None:
    try:
        value = Decimal(number.replace(",", ""))
    except InvalidOperation:
        return None
    if k:
        value *= 1000
    return str(value)


def _cut(text: str, m: re.Match) -> str:
    return text[:m.start()] + " " + text[m.end():]


def plan_question(question: str, known_sources: list[str]) -> Plan | Clarify:
    t = _normalise(question)
    if not t:
        return Clarify(HELP)

    if re.search(r"\bcompar(?:e|ing|ison)\b", t):
        ids = list(dict.fromkeys(int(n) for n in re.findall(r"\b\d{1,9}\b", t)))
        if 2 <= len(ids) <= 5:
            return Plan("compare_listings", {"listing_ids": ids})
        return Clarify("To compare, give me 2 to 5 listing ids, for example: compare 12 and 15.")

    if re.search(r"\balerts?\b", t):
        return Plan("list_alerts", {"unread_only": not re.search(r"\b(?:all|every|old|past)\b", t)})

    if re.search(r"\b(?:history|trend|price change|price drop|how has|changed|movement)\b", t):
        m = re.search(r"\b(\d{1,9})\b", t)
        if m:
            return Plan("get_price_history", {"listing_id": int(m.group(1))})
        return Clarify("Which listing? For example: price history of listing 12.")

    m = _LISTING_1.fullmatch(t) or _LISTING_2.fullmatch(t)
    if m:
        return Plan("get_listing", {"listing_id": int(m.group(1))})

    currency = None
    m = re.search(r"\b(inr|usd|eur)\b", t)
    if m:
        currency = m.group(1).upper()
        t = re.sub(r"\b(?:inr|usd|eur)\b", " ", t)

    pmin = pmax = None
    m = _BETWEEN.search(t)
    if m:
        pmin, pmax = _amount(m.group(1), m.group(2)), _amount(m.group(3), m.group(4))
        if pmin is not None and pmax is not None and Decimal(pmin) > Decimal(pmax):
            pmin, pmax = pmax, pmin
        t = _cut(t, m)
    else:
        m = _MAX.search(t)
        if m:
            pmax = _amount(m.group(1), m.group(2))
            t = _cut(t, m)
        m = _MIN.search(t)
        if m:
            pmin = _amount(m.group(1), m.group(2))
            t = _cut(t, m)

    availability = None
    if _OUT.search(t):
        availability = "out_of_stock"
        t = _OUT.sub(" ", t)
    elif _IN.search(t):
        availability = "in_stock"
        t = _IN.sub(" ", t)

    sort = order = None
    if _DESC.search(t):
        sort, order = "price", "desc"
        t = _DESC.sub(" ", t)
    elif _ASC.search(t):
        sort, order = "price", "asc"
        t = _ASC.sub(" ", t)

    limit = None
    m = re.search(r"\b(?:top|first)\s+(\d{1,2})\b", t)
    if m:
        limit = max(1, min(20, int(m.group(1))))
        t = _cut(t, m)

    source = None
    for name in known_sources:
        pattern = rf"\b{re.escape(name.lower())}\b"
        if re.search(pattern, t):
            source = name
            t = re.sub(pattern, " ", t)
            break

    words = [w.rstrip(".-") for w in re.findall(r"[a-z0-9][a-z0-9\-\.]*", t)]
    text = " ".join([w for w in words if w and w not in _STOP][:6])

    if not (text or source or availability or pmin or pmax or sort):
        return Clarify(HELP)

    args: dict[str, Any] = {}
    if text:
        args["text"] = text
    if source:
        args["source"] = source
    if availability:
        args["availability"] = availability
    if pmin is not None:
        args["min_price"] = pmin
    if pmax is not None:
        args["max_price"] = pmax
    if sort:
        args["sort"] = sort
        args["order"] = order
    if limit:
        args["limit"] = limit
    price_related = pmin is not None or pmax is not None or sort == "price"
    if price_related and currency:
        args["currency"] = currency
    return Plan("search_listings", args, needs_currency=price_related and currency is None)
