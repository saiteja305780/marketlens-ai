import streamlit as st

from dashboard.client import ApiError, delete, get, post


@st.cache_data(ttl=300)
def _title(listing_id: int) -> str:
    try:
        return get(f"/listings/{listing_id}")["title"]
    except ApiError:
        return f"Listing {listing_id}"


def render_alerts() -> None:
    st.caption("Rules fire once when the condition is met and do not repeat while it holds. "
               "Alerts appear after the system next checks your rules against fresh data.")

    st.subheader("Create a rule")
    q = st.text_input("Search for a listing to watch", key="al_q", placeholder="e.g. buds pro")
    options = {}
    if q.strip():
        try:
            found = get("/listings", {"q": q.strip(), "page_size": 25, "sort": "title",
                                      "order": "asc", "exclude_plans": "true"})
        except ApiError as exc:
            st.error(str(exc))
            return
        for it in found["items"]:
            latest = it.get("latest") or {}
            price = latest.get("price")
            shown = f"{price} {latest.get('currency') or ''}".strip() if price is not None else "no price"
            options[it["id"]] = f"{it['id']} | {it['title']} | {shown}"

    if options:
        listing_id = st.selectbox("Listing", list(options), format_func=lambda i: options[i], key="al_listing")
        rule_type = st.radio("Rule", ["price_below", "back_in_stock"], horizontal=True, key="al_type")
        threshold = 0.0
        if rule_type == "price_below":
            threshold = st.number_input("Alert when the price is at or below", min_value=0.0,
                                        value=0.0, step=100.0, key="al_thr")
        if st.button("Create rule"):
            if rule_type == "price_below" and threshold <= 0:
                st.error("Enter a price above 0 for a price_below rule.")
            else:
                body = {"listing_id": int(listing_id), "rule_type": rule_type}
                if rule_type == "price_below":
                    body["threshold"] = round(threshold, 2)
                try:
                    post("/alert-rules", body)
                    st.success("Rule created.")
                except ApiError as exc:
                    st.error(str(exc))
    elif q.strip():
        st.info("No listings matched that search.")

    st.divider()
    st.subheader("Active rules")
    try:
        rules = get("/alert-rules", {"active": "true", "page_size": 50})
    except ApiError as exc:
        st.error(str(exc))
        return
    if not rules["items"]:
        st.info("No active rules yet.")
    for r in rules["items"]:
        c1, c2, c3, c4 = st.columns([5, 2, 2, 1])
        c1.write(f"**{_title(r['listing_id'])}**  (listing {r['listing_id']})")
        if r["rule_type"] == "price_below":
            c2.write(f"Price at or below {r['threshold']} {r.get('currency') or ''}")
        else:
            c2.write("Back in stock")
        state = r.get("condition_met")
        c3.write("Not checked yet" if state is None else ("Condition met now" if state else "Condition not met"))
        if c4.button("Stop", key=f"deact_{r['id']}"):
            try:
                delete(f"/alert-rules/{r['id']}")
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.rerun()

    st.divider()
    st.subheader("Alerts")
    unread_only = st.checkbox("Unread only", value=True, key="al_unread")
    try:
        alerts = get("/alerts", {"unread_only": "true" if unread_only else "false", "page_size": 50})
    except ApiError as exc:
        st.error(str(exc))
        return
    if not alerts["items"]:
        st.info("No alerts to show.")
    for a in alerts["items"]:
        c1, c2 = st.columns([8, 1])
        c1.write(f"{a['created_at'][:16].replace('T', ' ')}: {a['message']}")
        if not a["is_read"] and c2.button("Read", key=f"read_{a['id']}"):
            try:
                post(f"/alerts/{a['id']}/read", {})
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.rerun()
    st.caption("Observed retailer prices. These are not verified discounts.")
