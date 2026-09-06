import requests
import streamlit as st

from utils.db import get_companies, get_documents

st.title("Annual Reports")

companies = get_companies()
names = dict(zip(companies["id"], companies["company_name"]))

query = st.text_input("Search company name or ticker")
matches = companies
if query:
    matches = companies[
        companies["id"].str.contains(query, case=False, na=False)
        | companies["company_name"].str.contains(query, case=False, na=False)
    ]

if query and matches.empty:
    st.warning("Ticker not found — please try another.")
    st.stop()

ticker = st.selectbox("Company", matches["id"], format_func=lambda t: f"{t} — {names[t]}")


@st.cache_data(ttl=600)
def _url_ok(url: str) -> bool:
    """DQ-13: report URL is live if HTTP 200 (HEAD first, then streamed GET)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        head = requests.head(
            url, timeout=8, allow_redirects=True, headers=headers
        )
        if head.status_code == 200:
            return True
        resp = requests.get(
            url, timeout=8, allow_redirects=True, stream=True, headers=headers
        )
        resp.close()
        return resp.status_code == 200
    except requests.RequestException:
        return False

docs = get_documents(ticker)
if docs.empty:
    st.info("No annual reports on record for this company.")
    st.stop()

for row in docs.itertuples(index=False):
    if row.Annual_Report and _url_ok(row.Annual_Report):
        st.markdown(f"**{row.Year}** — [Open BSE PDF]({row.Annual_Report})")
    else:
        st.markdown(f"**{row.Year}** — :red[Report unavailable]")