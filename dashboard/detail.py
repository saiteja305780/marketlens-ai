import pandas as pd
import streamlit as st

from dashboard.client import ApiError, get


def _num(value):
    return float(value) if value is not None else None


def render_detail(listing_id: int) -> None:
    try:
        listing = get(f"/listings/{listing_id}")
        history = get(f"/listings/{listing_id}/history")
    except ApiError as exc:
        st.error(str(exc))
        return

    st.divider()
    st.subheader(listing["title"])

    left, right = st.columns([1, 4])
    with left:
        if listing.get("image_url"):
            st.image(listing["image_url"], width=160)
    with right:
        bits = [f"Source: {listing['source']}"]
        if listing.get("brand"):
            bits.append(f"Brand: {listing['brand']}")
        if listing.get("category"):
            bits.append(f"Category: {listing['category']}")
        st.write("  |  ".join(bits))
        st.caption(
            f"First seen {listing['first_seen_at'][:10]}, last seen {listing['last_seen_at'][:10]}"
        )
        if listing["is_stale"]:
            st.warning("This listing has not been seen recently, so the price may be out of date.")
        st.link_button("Open on retailer site", listing["url"])

    stats = history.get("stats")
    if stats:
        cur = stats["currency"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Latest", f"{_num(stats['latest_price']):,.2f} {cur}")
        c2.metric("Lowest observed", f"{_num(stats['lowest_price']):,.2f} {cur}")
        c3.metric("Highest observed", f"{_num(stats['highest_price']):,.2f} {cur}")
        pct = _num(stats.get("percent_change"))
        c4.metric("Change since first seen", f"{pct:+.1f}%" if pct is not None else "n/a")
        st.caption(f"Based on {stats['observation_count']} observations.")

    for w in history.get("warnings", []):
        st.warning(w)

    points = [
        {"observed_at": o["observed_at"], "price": _num(o["price"]), "currency": o["currency"]}
        for o in history["observations"]
        if o.get("price") is not None
    ]
    if not points:
        st.info("No price observations for this listing yet.")
        return

    df = pd.DataFrame(points)
    df["observed_at"] = pd.to_datetime(df["observed_at"])
    main_currency = df["currency"].mode().iloc[0]
    df = df[df["currency"] == main_currency].sort_values("observed_at")

    st.markdown(f"**Observed price over time ({main_currency})**")
    st.line_chart(df.set_index("observed_at")["price"])
    if len(df) < 2:
        st.caption("Only one observation so far, so there is no trend to show yet.")
    st.caption("Observed retailer prices. These are not verified discounts.")
