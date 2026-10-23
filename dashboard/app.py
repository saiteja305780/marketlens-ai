import math

import streamlit as st

from dashboard.alerts_tab import render_alerts
from dashboard.ask_tab import render_ask
from dashboard.client import ApiError, get, get_text
from dashboard.compare_tab import render_compare
from dashboard.detail import render_detail

st.set_page_config(page_title="MarketLens AI", layout="wide")
st.title("MarketLens AI")
st.caption("Observed retailer prices. These are not verified discounts.")

try:
    sources = get("/sources")
except ApiError as exc:
    st.error(str(exc))
    st.stop()

currencies = sorted({s["currency"] for s in sources})

with st.sidebar:
    st.header("Browse filters")
    st.caption("These apply to the Browse tab.")
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

tab_browse, tab_compare, tab_ask, tab_alerts = st.tabs(["Browse", "Compare", "Ask", "Alerts"])

with tab_browse:
    with st.expander("Data sources"):
        st.dataframe(sources, width="stretch", hide_index=True)

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
    st.caption(f"{data['total']} matching listings, page {data['page']} of {pages}. Click a row to see its price history.")
    export_params = {k: v for k, v in params.items() if k not in ("page", "page_size")}
    export_sig = repr(sorted((k, str(v)) for k, v in export_params.items()))
    if st.button("Prepare CSV of all matching listings"):
        try:
            st.session_state["csv_listings"] = (export_sig, get_text("/exports/listings.csv", export_params))
        except ApiError as exc:
            st.error(str(exc))
    prepared = st.session_state.get("csv_listings")
    if prepared and prepared[0] == export_sig:
        st.download_button("Download CSV", prepared[1], file_name="listings.csv", mime="text/csv")

    if rows:
        event = st.dataframe(
            rows, width="stretch", hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={"link": st.column_config.LinkColumn("link", display_text="open")},
        )
        selected = event.selection.rows
        if selected:
            render_detail(rows[selected[0]]["id"])
    else:
        st.info("No listings to show for these filters.")

with tab_compare:
    render_compare()

with tab_ask:
    render_ask()

with tab_alerts:
    render_alerts()
