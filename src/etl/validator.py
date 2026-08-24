import logging
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

logger = logging.getLogger(__name__)

ANNUAL_TABLES = ("profitandloss", "balancesheet", "cashflow")
COLS = ["rule", "table", "company_id", "year", "field", "issue", "severity"]


def _empty() -> pd.DataFrame:
    """Return an empty violation frame."""
    return pd.DataFrame(columns=COLS)


def _emit(
    rule: str,
    table: str,
    company_id: object,
    year: object,
    field: str,
    issue: object,
    severity: str,
) -> pd.DataFrame:
    """Build a violation block from aligned series or scalars."""
    return pd.DataFrame(
        {
            "rule": rule,
            "table": table,
            "company_id": company_id,
            "year": year,
            "field": field,
            "issue": issue,
            "severity": severity,
        }
    )


def _head_status(url: str) -> int:
    """Return HTTP status for a URL, 0 on network failure."""
    try:
        return requests.head(url, timeout=5, allow_redirects=True).status_code
    except requests.RequestException:
        return 0


def dq01_company_pk(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-01: companies.id must be unique."""
    df = frames.get("companies", _empty())
    if df.empty:
        return _empty()
    mask = df["id"].duplicated(keep=False)
    return _emit(
        "DQ-01",
        "companies",
        df.loc[mask, "id"],
        "",
        "id",
        "duplicate company id",
        "CRITICAL",
    )


def dq02_annual_pk(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-02: (company_id, year) must be unique in annual tables."""
    parts = []
    for name in ANNUAL_TABLES:
        df = frames.get(name, _empty())
        if df.empty:
            continue
        mask = df.duplicated(subset=["company_id", "year"], keep=False)
        parts.append(
            _emit(
                "DQ-02",
                name,
                df.loc[mask, "company_id"],
                df.loc[mask, "year"],
                "company_id,year",
                "duplicate annual pk",
                "CRITICAL",
            )
        )
    return pd.concat(parts) if parts else _empty()


def dq03_fk_integrity(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-03: child company_id must exist in companies.id."""
    companies = frames.get("companies", _empty())
    valid = set(companies["id"]) if not companies.empty else set()
    parts = []
    for name, df in frames.items():
        if name == "companies" or df.empty or "company_id" not in df.columns:
            continue
        mask = ~df["company_id"].isin(valid)
        if mask.any():
            year = df.loc[mask, "year"] if "year" in df.columns else ""
            parts.append(
                _emit(
                    "DQ-03",
                    name,
                    df.loc[mask, "company_id"],
                    year,
                    "company_id",
                    "orphan company_id",
                    "CRITICAL",
                )
            )
    return pd.concat(parts) if parts else _empty()


def dq04_bs_balance(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-04: |assets - liabilities| / assets must be below 1%."""
    df = frames.get("balancesheet", _empty())
    if df.empty:
        return _empty()
    ta = pd.to_numeric(df["total_assets"], errors="coerce")
    tl = pd.to_numeric(df["total_liabilities"], errors="coerce")
    diff = (ta - tl).abs() / ta.replace(0, pd.NA)
    mask = (ta > 0) & (diff >= 0.01)
    return _emit(
        "DQ-04",
        "balancesheet",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "total_assets,total_liabilities",
        "bs imbalance " + diff[mask].map("{:.2%}".format).astype(str),
        "WARNING",
    )


def dq05_opm_crosscheck(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-05: source OPM must match computed OPM within 1pp."""
    df = frames.get("profitandloss", _empty())
    if df.empty:
        return _empty()
    opm = pd.to_numeric(df["opm_percentage"], errors="coerce")
    calc = (
        pd.to_numeric(df["operating_profit"], errors="coerce")
        / pd.to_numeric(df["sales"], errors="coerce").replace(0, pd.NA)
    ) * 100
    delta = (opm - calc).abs()
    mask = delta >= 1.0
    return _emit(
        "DQ-05",
        "profitandloss",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "opm_percentage",
        "opm delta " + delta[mask].round(2).astype(str),
        "WARNING",
    )


def dq06_positive_sales(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-06: sales must be positive."""
    df = frames.get("profitandloss", _empty())
    if df.empty:
        return _empty()
    mask = pd.to_numeric(df["sales"], errors="coerce") <= 0
    return _emit(
        "DQ-06",
        "profitandloss",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "sales",
        "sales <= 0",
        "WARNING",
    )


def dq07_year_format(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-07: normalised year must match YYYY-MM."""
    parts = []
    for name in ANNUAL_TABLES:
        df = frames.get(name, _empty())
        if df.empty:
            continue
        mask = ~df["year"].astype(str).str.fullmatch(r"\d{4}-\d{2}")
        if mask.any():
            parts.append(
                _emit(
                    "DQ-07",
                    name,
                    df.loc[mask, "company_id"],
                    df.loc[mask, "year"],
                    "year",
                    "bad year format",
                    "CRITICAL",
                )
            )
    return pd.concat(parts) if parts else _empty()


def dq08_ticker_format(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-08: ticker length must be 2-12 chars."""
    parts = []
    for name, df in frames.items():
        if df.empty:
            continue
        col = (
            "company_id"
            if "company_id" in df.columns
            else "id" if name == "companies" else None
        )
        if col is None:
            continue
        mask = ~df[col].astype(str).str.len().between(2, 12)
        if mask.any():
            parts.append(
                _emit(
                    "DQ-08",
                    name,
                    df.loc[mask, col],
                    "",
                    col,
                    "ticker length out of range",
                    "CRITICAL",
                )
            )
    return pd.concat(parts) if parts else _empty()


def dq09_net_cash_check(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-09: net cash flow must equal CFO+CFI+CFF within 10 Cr."""
    df = frames.get("cashflow", _empty())
    if df.empty:
        return _empty()
    ncf = pd.to_numeric(df["net_cash_flow"], errors="coerce")
    calc = (
        pd.to_numeric(df["operating_activity"], errors="coerce")
        + pd.to_numeric(df["investing_activity"], errors="coerce")
        + pd.to_numeric(df["financing_activity"], errors="coerce")
    )
    delta = (ncf - calc).abs()
    mask = delta > 10
    return _emit(
        "DQ-09",
        "cashflow",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "net_cash_flow",
        "cf mismatch " + delta[mask].round(2).astype(str),
        "WARNING",
    )


def dq10_fixed_assets(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-10: fixed assets must be non-negative."""
    df = frames.get("balancesheet", _empty())
    if df.empty:
        return _empty()
    mask = pd.to_numeric(df["fixed_assets"], errors="coerce") < 0
    return _emit(
        "DQ-10",
        "balancesheet",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "fixed_assets",
        "negative fixed assets",
        "WARNING",
    )


def dq11_tax_range(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-11: tax rate must be within 0-60."""
    df = frames.get("profitandloss", _empty())
    if df.empty:
        return _empty()
    tax = pd.to_numeric(df["tax_percentage"], errors="coerce")
    mask = (tax < 0) | (tax > 60)
    return _emit(
        "DQ-11",
        "profitandloss",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "tax_percentage",
        "tax out of range " + tax[mask].astype(str),
        "WARNING",
    )


def dq12_payout_cap(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-12: dividend payout must be <= 200."""
    df = frames.get("profitandloss", _empty())
    if df.empty:
        return _empty()
    dp = pd.to_numeric(df["dividend_payout"], errors="coerce")
    mask = dp > 200
    return _emit(
        "DQ-12",
        "profitandloss",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "dividend_payout",
        "payout > 200 " + dp[mask].astype(str),
        "WARNING",
    )


def dq13_url_validity(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-13: annual report URLs must return HTTP 200 (opt-in via URL_CHECK=true)."""
    df = frames.get("documents", _empty())
    if df.empty or os.getenv("URL_CHECK", "false").lower() != "true":
        return _empty()
    urls = df["Annual_Report"].dropna().astype(str)
    urls = urls[urls.str.startswith("http")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        codes = pd.Series(list(pool.map(_head_status, urls)), index=urls.index)
    mask = codes != 200
    return _emit(
        "DQ-13",
        "documents",
        df.loc[mask, "company_id"],
        df.loc[mask, "Year"],
        "Annual_Report",
        "http " + codes[mask].astype(str),
        "WARNING",
    )


def dq14_eps_sign(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-14: EPS must be positive when net profit is positive."""
    df = frames.get("profitandloss", _empty())
    if df.empty:
        return _empty()
    mask = (pd.to_numeric(df["net_profit"], errors="coerce") > 0) & (
        pd.to_numeric(df["eps"], errors="coerce") <= 0
    )
    return _emit(
        "DQ-14",
        "profitandloss",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "eps",
        "eps sign mismatch",
        "WARNING",
    )


def dq15_bs_strict(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-15: strict assets == liabilities counter (informational)."""
    df = frames.get("balancesheet", _empty())
    if df.empty:
        return _empty()
    ta = pd.to_numeric(df["total_assets"], errors="coerce")
    tl = pd.to_numeric(df["total_liabilities"], errors="coerce")
    mask = ta.notna() & tl.notna() & (ta != tl)
    return _emit(
        "DQ-15",
        "balancesheet",
        df.loc[mask, "company_id"],
        df.loc[mask, "year"],
        "total_assets,total_liabilities",
        "strict bs diff",
        "INFO",
    )


def dq16_coverage(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """DQ-16: each company needs >= 5 years per annual table."""
    parts = []
    for name in ANNUAL_TABLES:
        df = frames.get(name, _empty())
        if df.empty:
            continue
        counts = df.groupby("company_id")["year"].nunique()
        short = counts[counts < 5]
        if not short.empty:
            parts.append(
                _emit(
                    "DQ-16",
                    name,
                    pd.Series(short.index),
                    "",
                    "company_id",
                    "coverage " + short.astype(str) + " yrs",
                    "WARNING",
                )
            )
    return pd.concat(parts) if parts else _empty()


RULES = (
    dq01_company_pk,
    dq02_annual_pk,
    dq03_fk_integrity,
    dq04_bs_balance,
    dq05_opm_crosscheck,
    dq06_positive_sales,
    dq07_year_format,
    dq08_ticker_format,
    dq09_net_cash_check,
    dq10_fixed_assets,
    dq11_tax_range,
    dq12_payout_cap,
    dq13_url_validity,
    dq14_eps_sign,
    dq15_bs_strict,
    dq16_coverage,
)


def validate_all(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Run all 16 DQ rules and return the combined violation table."""
    return pd.concat([rule(frames) for rule in RULES], ignore_index=True)[COLS]
