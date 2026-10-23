import math

import streamlit as st

from dashboard.client import ApiError, get

st.set_page_config(page_title="MarketLens AI", layout="wide")
st.title("MarketLens AI")
st.caption("Observed retailer prices. These are not verified discounts.")

try:
    sources = get("/sources")
except ApiError as exc:
    st.error(str(exc))
    st.stop()

with st.expander("Data sources"):
    st.dataframe(sources, width="stretch", hide_index=True)

currencies = sorted({s["currency"] for s in sources})

with st.sidebar:
    st.header("Filters")
    q = st.text_input("Title contains", placeholder="e.g. buds pro")
    source = st.selectbox("Source", ["Any"] + [s["name"] for s in sources])
    availability = st.selectbox("Availability", ["Any", "in_stock", "out_of_stock", "unknown"])
    currency = st.selectbox("Currency (for price filters)", currencies)
    min_price = st.number_input("Min price (0 = no limit)", min_value=0.0, value=0.0, step=100.0)
    max_price = st.number_input("Max price (0 = no limit)", min_value=0.0, value=0.0, step=100.0)
    sort = st.selectbox("Sort by", ["title", "price", "last_seen_at", "first_seen_at"])
    order = st.radio("Order", ["asc", "desc"], horizontal=True)
    page_size = st.selectbox("Rows per page", [10, 25, 50], index=1)
    hide_plans = st.checkbox("Hide protection / warranty plans", value=True)

page = st.number_input("Page", min_value=1, value=1, step=1)

params = {
    "q": q.strip() or None,
    "source": None if source == "Any" else source,
    "availability": None if availability == "Any" else availability,
    "min_price": min_price if min_price > 0 else None,
    "max_price": max_price if max_price > 0 else None,
    "sort": sort,
    "order": order,
    "page": int(page),
    "page_size": page_size,
    "exclude_plans": "true" if hide_plans else "false",
}
if params["min_price"] is not None or params["max_price"] is not None:
    params["currency"] = currency

try:
    data = get("/listings", params)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

rows = []
for item in data["items"]:
    latest = item.get("latest") or {}
    price = latest.get("price")
    rows.append({
        "id": item["id"],
        "title": item["title"],
        "source": item["source"],
        "price": float(price) if price is not None else None,
        "currency": latest.get("currency"),
        "availability": (latest.get("availability") or "unknown").replace("_", " "),
        "not seen recently": item["is_stale"],
        "link": item["url"],
    })

pages = max(1, math.ceil(data["total"] / data["page_size"]))
st.caption(f"{data['total']} matching listings, page {data['page']} of {pages}")

if rows:
    st.dataframe(
        rows, width="stretch", hide_index=True,
        column_config={"link": st.column_config.LinkColumn("link", display_text="open")},
    )
else:
    st.info("No listings to show for these filters.")
