import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.db import get_all_ratios, get_companies

st.title("Trend Analysis")

METRICS = {
    "ROE %": "return_on_equity_pct",
    "ROCE %": "return_on_capital_pct",
    "Net Profit Margin %": "net_profit_margin_pct",
    "OPM %": "operating_profit_margin_pct",
    "D/E": "debt_to_equity",
    "Revenue CAGR 5Y %": "revenue_cagr_5yr",
    "PAT CAGR 5Y %": "pat_cagr_5yr",
    "EPS CAGR 5Y %": "eps_cagr_5yr",
    "FCF (₹ Cr)": "free_cash_flow_cr",
}

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

ticker = st.selectbox(
    "Company", matches["id"], format_func=lambda t: f"{t} — {names[t]}"
)
selected = st.multiselect(
    "Metrics (max 3)", list(METRICS), default=["ROE %"], max_selections=3
)

series = (
    get_all_ratios()[get_all_ratios()["company_id"] == ticker]
    .sort_values("year")
    .tail(10)
)

if series.empty:
    st.info("No ratio history available for this company.")
    st.stop()

if len(series) < 10:
    st.info(f"Partial data — {len(series)} years available for {ticker}.")

fig = go.Figure()
for label in selected:
    y = series[METRICS[label]]
    yoy = y.pct_change() * 100
    fig.add_trace(
        go.Scatter(
            x=series["year"].str[:4],
            y=y,
            name=label,
            mode="lines+markers+text",
            text=[f"{v:+.1f}%" if pd.notna(v) else "" for v in yoy],
            textposition="top center",
            textfont={"size": 9},
        )
    )
fig.update_layout(legend={"orientation": "h", "y": -0.15})
st.plotly_chart(fig, width="stretch")

st.download_button(
    "Download CSV",
    series[["year"] + [METRICS[s] for s in selected]]
    .to_csv(index=False)
    .encode(),
    file_name=f"{ticker}_trends.csv",
    mime="text/csv",
)