"""Cash flow KPI and capital allocation engine for the Nifty 100 platform."""

import logging
from pathlib import Path

import pandas as pd

from src.analytics.ratios import BASE_DIR, load_config, load_inputs, save_ratios

logger = logging.getLogger(__name__)

OUTPUT_PATH = BASE_DIR / "output" / "capital_allocation.csv"

CASHFLOW_COLUMNS = {
    "free_cash_flow_cr": "REAL",
    "cfo_quality_score": "REAL",
    "cfo_quality_label": "TEXT",
    "capex_intensity_pct": "REAL",
    "capex_intensity_label": "TEXT",
    "fcf_conversion_pct": "REAL",
    "capital_allocation_label": "TEXT",
}

PATTERN_LABELS = {
    ("+", "+", "+"): "Cash Accumulator",
    ("+", "+", "-"): "Liquidating Assets",
    ("+", "-", "+"): "Mixed",
    ("-", "+", "+"): "Distress Signal",
    ("-", "+", "-"): "Divestment",
    ("-", "-", "+"): "Growth Funded by Debt",
    ("-", "-", "-"): "Pre-Revenue",
}


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def _sign(value: float | None) -> str | None:
    """Return '+', '-' or '0' for a cash flow value; None if missing."""
    v = _num(value)
    if v is None:
        return None
    if v > 0:
        return "+"
    return "-" if v < 0 else "0"


def _lookback(year: str, window: int) -> str:
    """Return the YYYY-MM label window years before year."""
    return f"{int(year[:4]) - window}{year[4:]}"


def free_cash_flow(cfo: float | None, cfi: float | None) -> float | None:
    """Free cash flow = CFO + CFI; negative values allowed."""
    c = _num(cfo)
    i = _num(cfi)
    if c is None or i is None:
        return None
    return c + i


def cfo_quality_score(
    pairs: list[tuple[float | None, float | None]]
) -> float | None:
    """Average CFO/PAT over the window; None when current PAT is zero."""
    clean = [(_num(c), _num(p)) for c, p in pairs]
    if not clean or clean[-1][1] in (None, 0):
        return None
    ratios = [c / p for c, p in clean if c is not None and p not in (None, 0)]
    if not ratios:
        return None
    return sum(ratios) / len(ratios)


def cfo_quality_label(
    score: float | None, high: float, moderate: float
) -> str | None:
    """Tier label for the CFO quality score."""
    if score is None:
        return None
    if score > high:
        return "High Quality"
    if score >= moderate:
        return "Moderate"
    return "Accrual Risk"


def capex_intensity(
    investing_activity: float | None, sales: float | None
) -> float | None:
    """CapEx intensity percent; None when sales is zero or missing."""
    inv = _num(investing_activity)
    revenue = _num(sales)
    if inv is None or revenue in (None, 0):
        return None
    return abs(inv) / revenue * 100


def capex_intensity_label(
    value: float | None, light: float, intensive: float
) -> str | None:
    """Tier label for CapEx intensity."""
    if value is None:
        return None
    if value < light:
        return "Asset Light"
    if value <= intensive:
        return "Moderate"
    return "Capital Intensive"


def fcf_conversion(fcf: float | None, operating_profit: float | None) -> float | None:
    """FCF conversion percent; None when operating profit <= 0."""
    f = _num(fcf)
    op = _num(operating_profit)
    if f is None or op is None or op <= 0:
        return None
    return f / op * 100


def capital_allocation_label(
    cfo: float | None,
    cfi: float | None,
    cff: float | None,
    cfo_pat: float | None,
    shareholder_threshold: float,
) -> str | None:
    """Label the CFO/CFI/CFF sign pattern (8-class classifier)."""
    signs = (_sign(cfo), _sign(cfi), _sign(cff))
    if any(s is None for s in signs):
        return None
    if signs == ("+", "-", "-"):
        if cfo_pat is not None and cfo_pat > shareholder_threshold:
            return "Shareholder Returns"
        return "Reinvestor"
    return PATTERN_LABELS.get(signs, "Mixed")


def capital_allocation_frame(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Sign pattern table with 8-class labels per company-year."""
    pat = pd.to_numeric(df["net_profit"], errors="coerce")
    cfo_pat = (
        pd.to_numeric(df["operating_activity"], errors="coerce")
        .div(pat)
        .where(pat != 0)
    )
    return pd.DataFrame(
        {
            "company_id": df["company_id"].to_numpy(),
            "year": df["year"].to_numpy(),
            "cfo_sign": [_sign(v) for v in df["operating_activity"]],
            "cfi_sign": [_sign(v) for v in df["investing_activity"]],
            "cff_sign": [_sign(v) for v in df["financing_activity"]],
            "pattern_label": [
                capital_allocation_label(
                    c, i, f, ratio, config["shareholder_returns_cfo_pat"]
                )
                for c, i, f, ratio in zip(
                    df["operating_activity"],
                    df["investing_activity"],
                    df["financing_activity"],
                    cfo_pat,
                )
            ],
        }
    )


def compute_cashflow(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute cash flow KPIs for every company-year row."""
    rows = list(df.itertuples())
    lookup = {(r.company_id, r.year): r for r in rows}
    window = int(config["cfo_quality_window_years"])
    out = df[["company_id", "year"]].copy()
    out["free_cash_flow_cr"] = [
        free_cash_flow(r.operating_activity, r.investing_activity) for r in rows
    ]
    scores = []
    for row in rows:
        pairs = []
        for back in range(window - 1, -1, -1):
            past = lookup.get((row.company_id, _lookback(row.year, back)))
            pairs.append(
                (None, None)
                if past is None
                else (past.operating_activity, past.net_profit)
            )
        scores.append(cfo_quality_score(pairs))
    out["cfo_quality_score"] = scores
    out["cfo_quality_label"] = [
        cfo_quality_label(s, config["cfo_quality_high"], config["cfo_quality_moderate"])
        for s in scores
    ]
    out["capex_intensity_pct"] = [
        capex_intensity(r.investing_activity, r.sales) for r in rows
    ]
    out["capex_intensity_label"] = [
        capex_intensity_label(
            v, config["capex_asset_light_pct"], config["capex_capital_intensive_pct"]
        )
        for v in out["capex_intensity_pct"]
    ]
    out["fcf_conversion_pct"] = [
        fcf_conversion(f, r.operating_profit)
        for f, r in zip(out["free_cash_flow_cr"], rows)
    ]
    out["capital_allocation_label"] = capital_allocation_frame(df, config)[
        "pattern_label"
    ]
    return out


def main() -> None:
    """Run the Day 11 cash flow KPI pipeline."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    merged = load_inputs()
    frame = compute_cashflow(merged, config)
    save_ratios(frame, CASHFLOW_COLUMNS)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    capital_allocation_frame(merged, config).to_csv(OUTPUT_PATH, index=False)
    logger.info("Computed %d cash flow rows; wrote %s", len(frame), OUTPUT_PATH.name)


if __name__ == "__main__":
    main()