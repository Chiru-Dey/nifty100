"""Leverage and efficiency ratio engine for the Nifty 100 platform."""

import logging

import pandas as pd

from src.analytics.ratios import load_config, load_inputs, save_ratios

logger = logging.getLogger(__name__)

LEVERAGE_COLUMNS = {
    "debt_to_equity": "REAL",
    "high_leverage_flag": "INTEGER",
    "interest_coverage": "REAL",
    "icr_label": "TEXT",
    "icr_warning_flag": "INTEGER",
    "net_debt_cr": "REAL",
    "asset_turnover": "REAL",
}


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def debt_to_equity(
    borrowings: float | None,
    equity_capital: float | None,
    reserves: float | None,
) -> float | None:
    """Debt-to-equity; 0.0 when debt-free; None when equity <= 0."""
    debt = _num(borrowings) or 0.0
    if debt == 0:
        return 0.0
    equity = _num(equity_capital)
    if equity is None:
        return None
    equity += _num(reserves) or 0.0
    if equity <= 0:
        return None
    return debt / equity


def high_leverage_flag(de: float | None, sector: str | None, threshold: float) -> bool:
    """True when D/E exceeds threshold for non-Financials companies."""
    return de is not None and de > threshold and sector != "Financials"


def interest_coverage(
    operating_profit: float | None,
    other_income: float | None,
    interest: float | None,
) -> float | None:
    """Interest coverage; None when interest is zero or missing."""
    op = _num(operating_profit)
    charge = _num(interest)
    if op is None or charge in (None, 0):
        return None
    return (op + (_num(other_income) or 0.0)) / charge


def icr_label(icr: float | None, interest: float | None) -> str | None:
    """'Debt Free' display label when ICR is None due to zero interest."""
    if icr is None and _num(interest) == 0:
        return "Debt Free"
    return None


def icr_warning_flag(icr: float | None, threshold: float) -> bool:
    """True when ICR is below the coverage distress threshold."""
    return icr is not None and icr < threshold


def net_debt(borrowings: float | None, investments: float | None) -> float:
    """Net debt = borrowings less investments liquid asset proxy."""
    return (_num(borrowings) or 0.0) - (_num(investments) or 0.0)


def asset_turnover(sales: float | None, total_assets: float | None) -> float | None:
    """Asset turnover; None when total assets is zero or missing."""
    revenue = _num(sales)
    assets = _num(total_assets)
    if revenue is None or assets in (None, 0):
        return None
    return revenue / assets


def compute_leverage(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute leverage and efficiency KPIs for every company-year row."""
    out = df[["company_id", "year"]].copy()
    out["debt_to_equity"] = df.apply(
        lambda r: debt_to_equity(r.borrowings, r.equity_capital, r.reserves), axis=1
    )
    out["high_leverage_flag"] = [
        high_leverage_flag(d, s, config["high_leverage_de"])
        for d, s in zip(out["debt_to_equity"], df["broad_sector"])
    ]
    out["interest_coverage"] = df.apply(
        lambda r: interest_coverage(r.operating_profit, r.other_income, r.interest),
        axis=1,
    )
    out["icr_label"] = [
        icr_label(v, i) for v, i in zip(out["interest_coverage"], df["interest"])
    ]
    out["icr_warning_flag"] = [
        icr_warning_flag(v, config["icr_warning_threshold"])
        for v in out["interest_coverage"]
    ]
    out["net_debt_cr"] = df.apply(
        lambda r: net_debt(r.borrowings, r.investments), axis=1
    )
    out["asset_turnover"] = df.apply(
        lambda r: asset_turnover(r.sales, r.total_assets), axis=1
    )
    return out


def main() -> None:
    """Run the Day 9 leverage and efficiency ratio pipeline."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    merged = load_inputs()
    frame = compute_leverage(merged, config)
    save_ratios(frame, LEVERAGE_COLUMNS)
    logger.info(
        "Computed %d leverage rows; %d high-leverage flags",
        len(frame),
        int(frame["high_leverage_flag"].sum()),
    )


if __name__ == "__main__":
    main()