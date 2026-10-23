import streamlit as st

from dashboard.client import ApiError, get


def _num(value):
    return float(value) if value is not None else None


def render_compare() -> None:
    st.caption("Listings are not assumed to be the same product. Ranking only uses listings that share one currency.")
    labels = st.session_state.setdefault("cmp_labels", {})

    q = st.text_input("Search listings to add", key="cmp_q", placeholder="e.g. buds")
    if q.strip():
        try:
            found = get("/listings", {"q": q.strip(), "page_size": 50, "sort": "title",
                                      "order": "asc", "exclude_plans": "true"})
        except ApiError as exc:
            st.error(str(exc))
            return
        for it in found["items"]:
            latest = it.get("latest") or {}
            price = latest.get("price")
            shown = f"{price} {latest.get('currency') or ''}".strip() if price is not None else "no price"
            labels[it["id"]] = f"{it['id']} | {it['title']} | {shown}"

    chosen = st.multiselect("Pick 2 to 5 listings", options=list(labels.keys()),
                            format_func=lambda i: labels[i], key="cmp_sel", max_selections=5)
    if len(chosen) < 2:
        st.info("Search above and pick at least two listings. Your picks stay selected when you search again.")
        return

    try:
        data = get("/compare", {"ids": chosen})
    except ApiError as exc:
        st.error(str(exc))
        return

    for w in data.get("warnings", []):
        st.warning(w)

    if data.get("cheapest_listing_id") is not None:
        cheapest = next(i for i in data["items"] if i["listing"]["id"] == data["cheapest_listing_id"])
        c1, c2 = st.columns(2)
        c1.metric("Lowest latest price", cheapest["listing"]["title"][:40])
        spread = _num(data.get("price_spread"))
        c2.metric("Price spread", f"{spread:,.2f} {data['currency']}" if spread is not None else "n/a")

    rows = []
    for item in data["items"]:
        listing = item["listing"]
        stats = item.get("stats") or {}
        latest = listing.get("latest") or {}
        pct = _num(stats.get("percent_change"))
        rows.append({
            "rank": item.get("price_rank"),
            "id": listing["id"],
            "title": listing["title"],
            "source": listing["source"],
            "latest price": _num(latest.get("price")),
            "currency": latest.get("currency"),
            "lowest observed": _num(stats.get("lowest_price")),
            "highest observed": _num(stats.get("highest_price")),
            "change %": round(pct, 1) if pct is not None else None,
            "availability": (latest.get("availability") or "unknown").replace("_", " "),
            "link": listing["url"],
        })
    st.dataframe(rows, width="stretch", hide_index=True,
                 column_config={"link": st.column_config.LinkColumn("link", display_text="open")})

    for item in data["items"]:
        for w in item.get("stats_warnings", []):
            st.caption(f"Listing {item['listing']['id']}: {w}")
    st.caption("Observed retailer prices. These are not verified discounts.")
