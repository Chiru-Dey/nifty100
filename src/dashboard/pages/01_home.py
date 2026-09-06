import pandas as pd
import plotly.express as px
import streamlit as st

from utils.db import get_all_ratios, get_companies, get_market_caps
from utils.scoring import composite_score

st.title("Home / Overview")

year = st.sidebar.selectbox("Year", sorted(range(2019, 2025), reverse=True))

companies = get_companies()
ratios = get_all_ratios()
market_caps = get_market_caps()

yr_ratios = ratios[ratios["year"].str.startswith(str(year))]
yr_caps = market_caps[market_caps["year"] == year]


def _fmt(value: float, suffix: str = "", decimals: int = 1) -> str:
    return "—" if value is None or pd.isna(value) else f"{value:,.{decimals}f}{suffix}"


k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Average ROE", _fmt(yr_ratios["return_on_equity_pct"].mean(), "%"))
k2.metric("Median P/E", _fmt(yr_caps["pe_ratio"].median(), "×"))
k3.metric("Median D/E", _fmt(yr_ratios["debt_to_equity"].median(), "×", 2))
k4.metric("Total Companies", len(companies))
k5.metric("Median Rev CAGR 5Y", _fmt(yr_ratios["revenue_cagr_5yr"].median(), "%"))
k6.metric("Debt-Free Companies", int((yr_ratios["debt_to_equity"] == 0).sum()))

st.plotly_chart(
    px.pie(companies, names="broad_sector", hole=0.55, title="Sector Breakdown")
)

scored = yr_ratios.assign(composite_score=composite_score(yr_ratios))
top5 = scored.nlargest(5, "composite_score").merge(
    companies[["id", "company_name", "broad_sector"]],
    left_on="company_id",
    right_on="id",
    how="left",
)
st.subheader("Top 5 by Composite Quality Score")
st.dataframe(
    top5[
        ["company_name", "broad_sector", "composite_score",
         "return_on_equity_pct", "debt_to_equity"]
    ],
    width="stretch",
    hide_index=True,
)