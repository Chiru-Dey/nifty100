import plotly.graph_objects as go
import streamlit as st

from utils.db import get_capital_allocation, get_companies, get_market_caps

st.title("Capital Allocation Map")

cap = get_capital_allocation().sort_values("year").groupby("company_id").tail(1)
mc = get_market_caps()
mc = mc[mc["year"] == mc["year"].max()]
cap = cap.merge(mc[["company_id", "market_cap_crore"]], on="company_id", how="left")
cap = cap.merge(
    get_companies()[["id", "company_name"]],
    left_on="company_id",
    right_on="id",
    how="left",
)

patterns = sorted(cap["pattern_label"].unique())
pattern_set = set(patterns)
totals = cap.groupby("pattern_label")["market_cap_crore"].sum()

fig = go.Figure(
    go.Treemap(
        labels=patterns + cap["company_id"].tolist(),
        parents=[""] * len(patterns) + cap["pattern_label"].tolist(),
        values=[totals[p] for p in patterns] + cap["market_cap_crore"].fillna(0).tolist(),
        customdata=patterns + cap["pattern_label"].tolist(),
        branchvalues="total",
        textinfo="label",
        hovertemplate="%{label}<br>₹%{value:,.0f} Cr<extra>%{customdata}</extra>",
    )
)
fig.update_layout(margin={"t": 40, "l": 0, "r": 0, "b": 0})

state = st.plotly_chart(
    fig, on_select="rerun", selection_mode=("points",), key="cap_treemap"
)


def _pattern_from_point(point: dict) -> str | None:
    """Resolve the clicked treemap node to its pattern label."""
    cd = point.get("customdata")
    if isinstance(cd, list):
        cd = cd[0]
    if cd in pattern_set:
        return cd
    label = point.get("label")
    if label in pattern_set:
        return label
    row = cap[cap["company_id"] == label]
    return row["pattern_label"].iloc[0] if not row.empty else None


pattern = None
if state.selection.points:
    pattern = _pattern_from_point(state.selection.points[0])

if pattern:
    members = cap[cap["pattern_label"] == pattern].sort_values(
        "market_cap_crore", ascending=False
    )
    st.subheader(f"{pattern} — {len(members)} companies")
    st.dataframe(
        members[["company_id", "company_name", "market_cap_crore"]],
        width="stretch",
        hide_index=True,
    )
else:
    st.caption("Click a pattern tile to list its companies.")