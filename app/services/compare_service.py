"""Side-by-side comparison of retailer listings. Pure logic: no database, no network.
Listings are never assumed to be the same product, currencies are never mixed, and missing
or zero prices are never ranked."""
from app.schemas.api import ListingOut, ObservationOut
from app.schemas.compare import CompareItem, CompareOut
from app.services.price_service import compute_history_stats

SAME_PRODUCT_WARNING = ("these are retailer listings shown side by side; they are not verified to be "
                        "the same product")


def _usable_price(listing: ListingOut):
    latest = listing.latest
    if latest is None or latest.price is None or latest.price <= 0 or latest.currency is None:
        return None
    return latest.price


def build_comparison(listings: list[ListingOut], histories: dict[int, list[ObservationOut]]) -> CompareOut:
    items = []
    for listing in listings:
        stats, stats_warnings = compute_history_stats(histories.get(listing.id, []))
        items.append(CompareItem(listing=listing, stats=stats, stats_warnings=stats_warnings))

    warnings = [SAME_PRODUCT_WARNING]
    stale = [str(i.listing.id) for i in items if i.listing.is_stale]
    if stale:
        warnings.append(f"listing(s) {', '.join(stale)} have not been seen recently; "
                        "their prices may be out of date")

    priced = [(i, _usable_price(i.listing)) for i in items]
    priced = [(i, p) for i, p in priced if p is not None]
    if len(priced) < 2:
        warnings.append("fewer than two listings have a usable current price; no ranking was made")
        return CompareOut(items=items, warnings=warnings)

    currencies = {i.listing.latest.currency for i, _ in priced}
    if len(currencies) > 1:
        warnings.append(f"listings use several currencies ({', '.join(sorted(currencies))}); "
                        "no ranking or price difference was calculated")
        return CompareOut(items=items, warnings=warnings)

    currency = next(iter(currencies))
    prices = [p for _, p in priced]
    lowest = min(prices)
    for item, price in priced:
        item.price_rank = 1 + sum(1 for q in prices if q < price)

    winners = [i for i, p in priced if p == lowest]
    cheapest = winners[0].listing.id if len(winners) == 1 else None
    if len(winners) > 1:
        warnings.append("two or more listings share the lowest price")
    if any(w.listing.latest.availability != "in_stock" for w in winners):
        warnings.append("the lowest price is on a listing that is not shown as in stock")
    unranked = [str(i.listing.id) for i in items if i.price_rank is None]
    if unranked:
        warnings.append(f"listing(s) {', '.join(unranked)} have no usable current price and were not ranked")

    return CompareOut(items=items, currency=currency, cheapest_listing_id=cheapest,
                      price_spread=max(prices) - lowest, warnings=warnings)
