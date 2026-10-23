import streamlit as st

from dashboard.client import ApiError, post


def render_ask() -> None:
    st.caption("Answers come from read-only queries over your data. Try: cheapest noise earbuds under 1500 in stock")
    with st.form("ask_form"):
        question = st.text_input("Ask about listings", max_chars=300)
        submitted = st.form_submit_button("Ask")
    if not submitted:
        return
    if not question.strip():
        st.info("Type a question first.")
        return
    try:
        result = post("/assistant/ask", {"question": question.strip()})
    except ApiError as exc:
        st.error(str(exc))
        return
    st.write(result.get("answer", "No answer field in the response."))
    with st.expander("How this answer was produced"):
        st.json(result)
    st.caption("Observed retailer prices. These are not verified discounts.")
