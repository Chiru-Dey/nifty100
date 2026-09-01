from __future__ import annotations

import re

import pandas as pd

YEAR_RE = re.compile(r"^\d{4}-\d{2}$")

SEVERITIES: dict[str, str] = {
    "DQ-01": "CRITICAL", "DQ-02": "CRITICAL", "DQ-03": "CRITICAL",
    "DQ-04": "WARNING", "DQ-05": "WARNING", "DQ-06": "WARNING",
    "DQ-07": "CRITICAL", "DQ-08": "CRITICAL", "DQ-09": "WARNING",
    "DQ-10": "WARNING", "DQ-11": "WARNING", "DQ-12": "WARNING",
    "DQ-13": "WARNING", "DQ-14": "WARNING",
}


def dq01_company_pk_unique(companies: pd.DataFrame) -> bool:
    """Violation when company PKs are duplicated."""
    return len(companies) != companies["id"].nunique()


def dq02_annual_pk_unique(frame: pd.DataFrame) -> pd.Series:
    """Violation rows for duplicate (company_id, year) pairs."""
    return frame.duplicated(subset=["company_id", "year"], keep="last")


def dq03_fk_integrity(child: pd.DataFrame, companies: pd.DataFrame) -> pd.Series:
    """Violation rows whose company_id has no parent."""
    return ~child["company_id"].isin(companies["id"])


def dq04_bs_balance(frame: pd.DataFrame, tol: float = 0.01) -> pd.Series:
    """Violation when assets vs liabilities diverge beyond tolerance."""
    assets = pd.to_numeric(frame["total_assets"], errors="coerce")
    liab = pd.to_numeric(frame["total_liabilities"], errors="coerce")
    return ((assets - liab).abs() / assets.replace(0, float("nan"))) > tol


def dq05_opm_cross_check(frame: pd.DataFrame, tol: float = 1.0) -> pd.Series:
    """Violation when source OPM deviates from computed OPM."""
    computed = pd.to_numeric(frame["operating_profit"], errors="coerce") / pd.to_numeric(frame["sales"], errors="coerce") * 100
    return (pd.to_numeric(frame["opm_percentage"], errors="coerce") - computed).abs() > tol


def dq06_positive_sales(frame: pd.DataFrame) -> pd.Series:
    """Violation rows with non-positive sales."""
    return pd.to_numeric(frame["sales"], errors="coerce") <= 0


def dq07_year_format(frame: pd.DataFrame) -> pd.Series:
    """Violation rows whose year is not YYYY-MM."""
    return ~frame["year"].astype(str).str.fullmatch(YEAR_RE)


def dq08_ticker_format(frame: pd.DataFrame) -> pd.Series:
    """Violation rows whose normalised ticker length is outside 2-12."""
    norm = frame["company_id"].astype(str).str.strip().str.upper()
    return ~norm.str.len().between(2, 12)


def dq09_net_cash_check(frame: pd.DataFrame, tol: float = 10) -> pd.Series:
    """Violation when net cash flow deviates from CFO+CFI+CFF."""
    total = (
        pd.to_numeric(frame["operating_activity"], errors="coerce")
        + pd.to_numeric(frame["investing_activity"], errors="coerce")
        + pd.to_numeric(frame["financing_activity"], errors="coerce")
    )
    return (pd.to_numeric(frame["net_cash_flow"], errors="coerce") - total).abs() > tol


def dq10_non_negative_fixed_assets(frame: pd.DataFrame) -> pd.Series:
    """Violation rows with negative fixed assets."""
    return pd.to_numeric(frame["fixed_assets"], errors="coerce") < 0


def dq11_tax_rate_range(frame: pd.DataFrame) -> pd.Series:
    """Violation rows with tax rate outside 0-60."""
    tax = pd.to_numeric(frame["tax_percentage"], errors="coerce")
    return (tax < 0) | (tax > 60)


def dq12_dividend_payout_cap(frame: pd.DataFrame) -> pd.Series:
    """Violation rows with dividend payout above 200%."""
    return pd.to_numeric(frame["dividend_payout"], errors="coerce") > 200


def dq13_url_validity(status_codes: pd.Series) -> pd.Series:
    """Violation when an annual report URL does not return HTTP 200."""
    return status_codes != 200


def dq14_eps_sign_consistency(frame: pd.DataFrame) -> pd.Series:
    """Violation when profitable company shows non-positive EPS."""
    return (pd.to_numeric(frame["net_profit"], errors="coerce") > 0) & ~(pd.to_numeric(frame["eps"], errors="coerce") > 0)