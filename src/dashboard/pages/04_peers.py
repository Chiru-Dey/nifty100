import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.db import get_all_ratios, get_peers

st.title("Peer Comparison")

METRICS = [
    ("ROE", "return_on_equity_pct", True),
    ("ROCE", "return_on_capital_pct", True),
    ("NPM", "net_profit_margin_pct", True),
    ("D/E", "debt_to_equity", False),
    ("FCF", "free_cash_flow_cr", True),
    ("PAT CAGR", "pat_cagr_5yr", True),
    ("Rev CAGR", "revenue_cagr_5yr", True),
    ("EPS CAGR", "eps_cagr_5yr", True),
]

peers = get_peers()
group = st.selectbox("Peer group", sorted(peers["peer_group_name"].unique()))
group_df = peers[peers["peer_group_name"] == group]
members = group_df["company_id"].tolist()
benchmark = (
    group_df["benchmark"].dropna().iloc[0]
    if "benchmark" in group_df.columns and group_df["benchmark"].notna().any()
    else None
)

snap = get_all_ratios().sort_values("year").groupby("company_id").tail(1)
snap = snap[snap["company_id"].isin(members)]


def _norm(s: pd.Series, higher_better: bool) -> pd.Series:
    """Min-max scale a series to 0-100 within the peer group."""
    lo, hi = s.min(), s.max()
    if not pd.notna(lo) or lo == hi:
        return pd.Series(50.0, index=s.index)
    scaled = (s - lo) / (hi - lo) * 100
    return (scaled if higher_better else 100 - scaled).fillna(50.0)


scaled = snap.copy()
for label, col, higher in METRICS:
    scaled[label] = _norm(snap[col], higher)

labels = [label for label, _, _ in METRICS]
default_idx = members.index(benchmark) if benchmark in members else 0
ticker = st.selectbox("Company", members, index=default_idx)

company = scaled[scaled["company_id"] == ticker].iloc[0]
average = scaled[labels].mean()

fig = go.Figure()
fig.add_trace(
    go.Scatterpolar(r=company[labels], theta=labels, fill="toself", name=ticker)
)
fig.add_trace(
    go.Scatterpolar(r=average[labels], theta=labels, fill="toself",
                    name="Group average")
)
fig.update_layout(
    polar={"radialaxis": {"range": [0, 100]}},
    legend={"orientation": "h", "y": -0.1},
    title="Company vs Peer Group Average (0-100 within-group scale, D/E inverted)",
)
st.plotly_chart(fig)

table = (
    snap[["company_id"] + [col for _, col, _ in METRICS]]
    .reset_index(drop=True)
    .round(2)
)


def _highlight(row: pd.Series) -> list[str]:
    """Highlight the benchmark company row."""
    colour = "background-color: #ffe9a8" if row["company_id"] == benchmark else ""
    return [colour] * len(row)


st.dataframe(table.style.apply(_highlight, axis=1), width="stretch", hide_index=True)
if benchmark:
    st.caption(f"Benchmark: {benchmark} (highlighted)")