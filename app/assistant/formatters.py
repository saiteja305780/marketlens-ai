"""Plain-text answers built from tool results with fixed templates. No model is involved, so every
number shown is exactly what a tool returned."""
from typing import Any

NOTE = "Prices are the latest ones we observed; they are not verified discounts."


def _price(latest: dict | None) -> str:
    if not latest or latest.get("price") is None:
        return "no price"
    return f"{latest['price']} {latest.get('currency') or ''}".strip()


def _availability(latest: dict | None) -> str:
    return str((latest or {}).get("availability") or "unknown").replace("_", " ")


def _line(listing: dict) -> str:
    stale = ", not seen recently" if listing.get("is_stale") else ""
    latest = listing.get("latest")
    return (f"- #{listing['id']} {listing['title']} ({listing['source']}): "
            f"{_price(latest)}, {_availability(latest)}{stale}")


def format_search(result: dict[str, Any], args: dict[str, Any]) -> str:
    total, shown = result["total_matches"], result["returned"]
    if total == 0:
        return "I found no listings matching that."
    head = f"Found {total} listing{'s' if total != 1 else ''}"
    if total > shown:
        head += f" (showing the first {shown})"
    return "\n".join([head + ":"] + [_line(l) for l in result["listings"]] + [NOTE])


def format_listing(result: dict[str, Any], args: dict[str, Any]) -> str:
    if not result["found"]:
        return "I couldn't find a listing with that id."
    l = result["listing"]
    latest = l.get("latest") or {}
    lines = [f"#{l['id']} {l['title']} ({l['source']})",
             f"Latest observed price: {_price(latest)}; availability: {_availability(latest)}."]
    if latest.get("list_price"):
        lines.append(f"The retailer advertises a compare-at price of {latest['list_price']}; "
                     "that is not proof of a discount.")
    seen = f"First seen {l['first_seen_at'][:10]}, last seen {l['last_seen_at'][:10]}"
    lines.append(seen + (" (not seen recently, so the price may be out of date)." if l.get("is_stale") else "."))
    lines.append(l["url"])
    return "\n".join(lines)


def format_history(result: dict[str, Any], args: dict[str, Any]) -> str:
    if not result["found"]:
        return "I couldn't find a listing with that id."
    stats = result.get("stats")
    if result["insufficient_data"]:
        n = stats["observation_count"] if stats else 0
        text = (f"I only have {n} priced observation{'s' if n != 1 else ''} for this listing so far, "
                "which is not enough to describe a price trend.")
        if stats:
            text += f" The latest observed price is {stats['latest_price']} {stats['currency']}."
        elif result.get("warnings"):
            text += " " + "; ".join(result["warnings"]) + "."
        return text
    lines = [f"{stats['observation_count']} priced observations from {stats['first_observed_at'][:10]} "
             f"to {stats['latest_observed_at'][:10]} ({stats['currency']}):",
             f"- first {stats['first_price']}, latest {stats['latest_price']}",
             f"- lowest {stats['lowest_price']}, highest {stats['highest_price']}"]
    if stats.get("absolute_change") is not None:
        lines.append(f"- change {stats['absolute_change']} ({stats['percent_change']}%)")
    lines.append("These are observed prices, not verified discounts.")
    return "\n".join(lines)


def format_compare(result: dict[str, Any], args: dict[str, Any]) -> str:
    if not result["found"]:
        return "I couldn't find listing(s): " + ", ".join(str(i) for i in result["missing_listing_ids"]) + "."
    c = result["comparison"]
    items = sorted(c["items"], key=lambda i: (i["price_rank"] is None, i["price_rank"] or 0, i["listing"]["id"]))
    lines = ["Side by side:"]
    for i in items:
        l = i["listing"]
        rank = f"{i['price_rank']}." if i["price_rank"] else "-"
        lines.append(f"{rank} #{l['id']} {l['title']}: {_price(l.get('latest'))}, {_availability(l.get('latest'))}")
    if c.get("cheapest_listing_id") is not None:
        lines.append(f"Lowest price: #{c['cheapest_listing_id']}; the spread between highest and lowest "
                     f"is {c['price_spread']} {c['currency']}.")
    lines += [f"Note: {w}" for w in c["warnings"]]
    return "\n".join(lines)


def format_alerts(result: dict[str, Any], args: dict[str, Any]) -> str:
    if result["total"] == 0:
        return "There are no alerts to show."
    return "\n".join([f"{result['total']} alert(s):"] + [f"- {a['message']}" for a in result["alerts"]])


FORMATTERS = {"search_listings": format_search, "get_listing": format_listing,
              "get_price_history": format_history, "compare_listings": format_compare,
              "list_alerts": format_alerts}
