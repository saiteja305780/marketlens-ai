import math
import re

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

with st.sidebar:
    st.header("Filters")
    q = st.text_input("Title contains", placeholder="e.g. buds pro")
    source = st.selectbox("Source", ["Any"] + [s["name"] for s in sources])
    availability = st.selectbox("Availability", ["Any", "in_stock", "out_of_stock", "unknown"])
    sort = st.selectbox("Sort by", ["title", "price", "last_seen_at", "first_seen_at"])
    order = st.radio("Order", ["asc", "desc"], horizontal=True)
    page_size = st.selectbox("Rows per page", [10, 25, 50], index=1)
    hide_plans = st.checkbox("Hide protection / warranty plans", value=True)

page = st.number_input("Page", min_value=1, value=1, step=1)

params = {
    "q": q.strip() or None,
    "source": None if source == "Any" else source,
    "availability": None if availability == "Any" else availability,
    "sort": sort,
    "order": order,
    "page": int(page),
    "page_size": page_size,
}

try:
    data = get("/listings", params)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

PLAN = re.compile(r"protection plan|warranty plan", re.I)
rows, hidden = [], 0
for item in data["items"]:
    if hide_plans and PLAN.search(item["title"]):
        hidden += 1
        continue
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
st.caption(f"{data['total']} matching listings, page {data['page']} of {pages}"
           + (f" ({hidden} plan listings hidden on this page)" if hidden else ""))

if rows:
    st.dataframe(
        rows, width="stretch", hide_index=True,
        column_config={"link": st.column_config.LinkColumn("link", display_text="open")},
    )
else:
    st.info("No listings to show for these filters.")
