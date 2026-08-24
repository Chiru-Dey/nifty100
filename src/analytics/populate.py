"""Full financial_ratios population orchestrator for the Nifty 100 platform."""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.cagr import CAGR_COLUMNS, compute_cagr
from src.analytics.cashflow_kpis import CASHFLOW_COLUMNS, compute_cashflow
from src.analytics.leverage import LEVERAGE_COLUMNS, compute_leverage
from src.analytics.ratios import (
    DB_PATH,
    RATIO_COLUMNS,
    compute_profitability,
    load_config,
    load_inputs,
    save_ratios,
)

logger = logging.getLogger(__name__)

MIN_ROW_COUNT = 1100
SPOT_TICKERS = ("TCS", "HDFCBANK", "RELIANCE")

BASE_COLUMNS = {
    "capex_cr": "REAL",
    "earnings_per_share": "REAL",
    "book_value_per_share": "REAL",
    "dividend_payout_ratio_pct": "REAL",
    "total_debt_cr": "REAL",
    "cash_from_operations_cr": "REAL",
    "composite_quality_score": "REAL",
}

ALL_COLUMNS = {
    **RATIO_COLUMNS,
    **LEVERAGE_COLUMNS,
    **CAGR_COLUMNS,
    **CASHFLOW_COLUMNS,
    **BASE_COLUMNS,
}


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def book_value_per_share(
    equity_capital: float | None,
    reserves: float | None,
    face_value: float | None,
) -> float | None:
    """Book value per share; None when share count is zero or missing."""
    equity = _num(equity_capital)
    face = _num(face_value)
    if equity is None or face in (None, 0):
        return None
    shares = equity / face
    if shares <= 0:
        return None
    return (equity + (_num(reserves) or 0.0)) / shares


def compute_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Passthrough KPI columns aligned with financial_ratios.xlsx schema."""
    out = df[["company_id", "year"]].copy()
    out["capex_cr"] = [
        abs(v) if pd.notna(v) else None for v in df["investing_activity"]
    ]
    out["earnings_per_share"] = df["eps"].to_numpy()
    out["dividend_payout_ratio_pct"] = df["dividend_payout"].to_numpy()
    out["total_debt_cr"] = df["borrowings"].to_numpy()
    out["cash_from_operations_cr"] = df["operating_activity"].to_numpy()
    out["book_value_per_share"] = [
        book_value_per_share(e, r, f)
        for e, r, f in zip(df["equity_capital"], df["reserves"], df["face_value"])
    ]
    return out


def _winsorise_scale(series: pd.Series, higher_better: bool = True) -> pd.Series:
    """Scale a series to 0-100 with P10/P90 winsorisation."""
    lo, hi = series.quantile(0.10), series.quantile(0.90)
    if hi <= lo:
        scaled = pd.Series(50.0, index=series.index)
    else:
        scaled = (series.clip(lo, hi) - lo) / (hi - lo) * 100
    if not higher_better:
        scaled = 100 - scaled
    return scaled.where(series.notna())

def composite_quality_score(frame: pd.DataFrame) -> pd.Series:
    """Weighted 0-100 score: 30% ROE, 25% FCF margin, 25% ROCE, 20% inverse D/E."""
    components = pd.DataFrame(
        {
            "roe": _winsorise_scale(
                pd.to_numeric(frame["return_on_equity_pct"], errors="coerce")
            ),
            "fcf": _winsorise_scale(
                pd.to_numeric(frame["free_cash_flow_cr"], errors="coerce")
                / pd.to_numeric(frame["sales"], errors="coerce")
                * 100
            ),
            "roce": _winsorise_scale(
                pd.to_numeric(frame["return_on_capital_pct"], errors="coerce")
            ),
            "de": _winsorise_scale(
                pd.to_numeric(frame["debt_to_equity"], errors="coerce"),
                higher_better=False,
            ),
        }
    )
    score = (
        0.30 * components["roe"]
        + 0.25 * components["fcf"]
        + 0.25 * components["roce"]
        + 0.20 * components["de"]
    )
    return score.where(components.notna().all(axis=1))


def build_full_frame(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Combine all ratio module outputs into one company-year frame."""
    full = compute_profitability(df, config["roce_benchmarks"])
    for frame in (
        compute_leverage(df, config),
        compute_cagr(df),
        compute_cashflow(df, config),
        compute_base_columns(df),
    ):
        full = full.merge(frame, on=["company_id", "year"])
    full = full.merge(df[["company_id", "year", "sales"]], on=["company_id", "year"])
    full["composite_quality_score"] = composite_quality_score(full)
    return full


def verify_row_count(db_path: Path = DB_PATH) -> int:
    """Return financial_ratios row count and log the AC-04 gate result."""
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    if count < MIN_ROW_COUNT:
        logger.error("AC-04 failed: %d rows < %d", count, MIN_ROW_COUNT)
    else:
        logger.info("AC-04 passed: %d rows >= %d", count, MIN_ROW_COUNT)
    return count


def spot_check(db_path: Path = DB_PATH) -> pd.DataFrame:
    """ROE and 5yr revenue CAGR history for manual spreadsheet comparison."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql(
            "SELECT company_id, year, return_on_equity_pct, revenue_cagr_5yr "
            "FROM financial_ratios WHERE company_id IN (?, ?, ?) "
            "ORDER BY company_id, year",
            conn,
            params=SPOT_TICKERS,
        )


def main() -> None:
    """Populate financial_ratios for all 92 companies and verify gates."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    frame = build_full_frame(load_inputs(), config)
    save_ratios(frame, ALL_COLUMNS)
    verify_row_count()
    logger.info(
        "Spot-check rows for manual spreadsheet comparison:\n%s",
        spot_check().round(4).to_string(index=False),
    )


if __name__ == "__main__":
    main()