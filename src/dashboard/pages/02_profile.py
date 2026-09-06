import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from utils.db import get_companies, get_pl, get_pros_cons, get_ratios

st.title("Company Profile")

companies = get_companies()
names = dict(zip(companies["id"], companies["company_name"]))

query = st.text_input("Search company name or ticker", placeholder="TCS or Tata")
matches = companies
if query:
    matches = companies[
        companies["id"].str.contains(query, case=False, na=False)
        | companies["company_name"].str.contains(query, case=False, na=False)
    ]

if query and matches.empty:
    st.warning("Ticker not found — please try another.")
    st.stop()

ticker = st.selectbox(
    "Company", matches["id"], format_func=lambda t: f"{t} — {names[t]}"
)


def _fmt(value: float, suffix: str = "") -> str:
    return "N/A" if value is None or pd.isna(value) else f"{value:,.1f}{suffix}"


row = companies[companies["id"] == ticker].iloc[0]
with st.container(border=True):
    st.markdown(f"### {row['company_name']}  `{ticker}`")
    st.markdown(
        f"**Sector:** {row['broad_sector']} · **Sub-sector:** {row['sub_sector']}"
    )
    st.caption(row["about_company"] or "No description available.")

ratios = get_ratios(ticker)
if 0 < len(ratios) < 10:
    st.info(f"Partial data — {len(ratios)} years available for {ticker}.")
elif ratios.empty:
    st.warning("No computed ratios available for this company.")

latest = ratios.iloc[-1] if not ratios.empty else pd.Series(dtype=float)

t1, t2, t3, t4, t5, t6 = st.columns(6)
t1.metric("ROE", _fmt(latest.get("return_on_equity_pct"), "%"))
t2.metric("ROCE", _fmt(latest.get("return_on_capital_pct"), "%"))
t3.metric("Net Profit Margin", _fmt(latest.get("net_profit_margin_pct"), "%"))
t4.metric("D/E", _fmt(latest.get("debt_to_equity"), "×"))
t5.metric("Revenue CAGR 5Y", _fmt(latest.get("revenue_cagr_5yr"), "%"))
t6.metric("FCF (₹ Cr)", _fmt(latest.get("free_cash_flow_cr")))

pl = get_pl(ticker).tail(10).copy()
if pl.empty:
    st.info("No P&L history available.")
else:
    pl["fy"] = pl["year"].str[:4]
    st.plotly_chart(
        px.bar(
            pl, x="fy", y=["sales", "net_profit"], barmode="group",
            title="Revenue vs Net Profit (10Y, ₹ Crore)",
        ),
        width="stretch",
    )

if ratios.empty:
    st.info("No ratio history available for charts.")
else:
    r10 = ratios.tail(10)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=r10["year"].str[:4], y=r10["return_on_equity_pct"],
                   name="ROE %", mode="lines+markers"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=r10["year"].str[:4], y=r10["return_on_capital_pct"],
                   name="ROCE %", mode="lines+markers"),
        secondary_y=True,
    )
    fig.update_layout(title="ROE vs ROCE (10Y)")
    st.plotly_chart(fig, width="stretch")

pc = get_pros_cons(ticker)
if pc.empty:
    st.info("No qualitative notes available for this company yet.")
else:
    left, right = st.columns(2)
    left.subheader("Pros")
    for text in pc["pros"].dropna():
        left.markdown(f":green[✅ {text}]")
    right.subheader("Cons")
    for text in pc["cons"].dropna():
        right.markdown(f":red[❌ {text}]")