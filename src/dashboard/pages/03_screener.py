import streamlit as st

from utils.db import get_all_ratios, get_companies, get_market_caps
from utils.scoring import composite_score

st.title("Financial Screener")

SLIDERS = [
    ("roe_min", "Min ROE %", 0, 50, 1),
    ("de_max", "Max D/E", 0.0, 20.0, 0.1),
    ("fcf_min", "Min FCF (₹ Cr)", -50000, 100000, 1000),
    ("rev_cagr_min", "Min Revenue CAGR 5Y %", -20, 50, 1),
    ("pat_cagr_min", "Min PAT CAGR 5Y %", -30, 60, 1),
    ("opm_min", "Min OPM %", 0, 60, 1),
    ("pe_max", "Max P/E", 0, 100, 1),
    ("pb_max", "Max P/B", 0.0, 20.0, 0.5),
    ("dy_min", "Min Dividend Yield %", 0.0, 5.0, 0.1),
    ("icr_min", "Min ICR", 0, 50, 1),
]
DEFAULTS = {k: (hi if k.endswith("_max") else lo) for k, _, lo, hi, _ in SLIDERS}

PRESETS = {
    "Quality": {"roe_min": 15, "de_max": 1.0, "fcf_min": 0, "rev_cagr_min": 10},
    "Value": {"de_max": 2.0, "pe_max": 20, "pb_max": 3.0, "dy_min": 1.0},
    "Growth": {"de_max": 2.0, "rev_cagr_min": 15, "pat_cagr_min": 20},
    "Dividend": {"fcf_min": 0, "dy_min": 2.0},
    "Debt-Free": {"roe_min": 12, "de_max": 0.0},
    "Turnaround": {"fcf_min": 0, "rev_cagr_min": 10},
}

cols = st.columns(len(PRESETS))
for col, (name, values) in zip(cols, PRESETS.items()):
    if col.button(name):
        st.session_state.update({**DEFAULTS, **values})

for key, default in DEFAULTS.items():
    st.session_state.setdefault(key, default)

v = {}
for key, label, lo, hi, step in SLIDERS:
    v[key] = st.sidebar.slider(label, lo, hi, step=step, key=key)

ratios = get_all_ratios().sort_values("year")
snap = ratios.groupby("company_id").tail(1).copy()
snap["composite_score"] = composite_score(snap)
mc = get_market_caps()
snap = snap.merge(
    mc[mc["year"] == mc["year"].max()][
        ["company_id", "pe_ratio", "pb_ratio", "dividend_yield_pct"]
    ],
    on="company_id",
    how="left",
)

mask = (
    (snap["return_on_equity_pct"] >= v["roe_min"])
    & (snap["debt_to_equity"] <= v["de_max"])
    & (snap["free_cash_flow_cr"] >= v["fcf_min"])
    & (snap["revenue_cagr_5yr"] >= v["rev_cagr_min"])
    & (snap["pat_cagr_5yr"] >= v["pat_cagr_min"])
    & (snap["operating_profit_margin_pct"] >= v["opm_min"])
    & (snap["pe_ratio"] <= v["pe_max"])
    & (snap["pb_ratio"] <= v["pb_max"])
    & (snap["dividend_yield_pct"] >= v["dy_min"])
    & ((snap["interest_coverage"] >= v["icr_min"]) | snap["interest_coverage"].isna())
)

companies = get_companies()
results = (
    snap[mask]
    .merge(
        companies[["id", "company_name", "broad_sector"]],
        left_on="company_id",
        right_on="id",
        how="left",
    )
    .sort_values("composite_score", ascending=False)
)

DISPLAY = [
    "company_id", "company_name", "broad_sector", "composite_score",
    "return_on_equity_pct", "debt_to_equity", "free_cash_flow_cr",
    "revenue_cagr_5yr", "pat_cagr_5yr", "operating_profit_margin_pct",
    "pe_ratio", "pb_ratio", "dividend_yield_pct", "interest_coverage",
]

st.markdown(f"**{len(results)}** companies match your filters")
st.dataframe(results[DISPLAY], width="stretch", hide_index=True)
st.download_button(
    "Download CSV",
    results[DISPLAY].to_csv(index=False).encode(),
    file_name="screener_results.csv",
    mime="text/csv",
)