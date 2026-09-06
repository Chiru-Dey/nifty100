import os
import sqlite3
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/nifty100.db")

_PATTERNS = {
    ("+", "-", "-"): "Reinvestor",
    ("+", "-", "+"): "Funded Expansion",
    ("+", "+", "-"): "Harvest & Return",
    ("+", "+", "+"): "Cash Builder",
    ("-", "-", "+"): "Distress",
    ("-", "+", "-"): "Asset Sale Funding",
    ("-", "+", "+"): "Equity Dependent",
    ("-", "-", "-"): "Cash Burn",
}


def _read(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only SQL query and return a DataFrame."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=600)
def get_companies() -> pd.DataFrame:
    """All 92 companies joined with sector mapping."""
    return _read(
        """
        SELECT c.*, s.broad_sector, s.sub_sector, s.market_cap_category
        FROM companies c
        LEFT JOIN sectors s ON s.company_id = c.id
        ORDER BY c.id
        """
    )


@st.cache_data(ttl=600)
def get_ratios(ticker: str, year: Optional[str] = None) -> pd.DataFrame:
    """Computed KPI history for one company, optionally a single year."""
    sql = "SELECT * FROM financial_ratios WHERE company_id = ?"
    params = [ticker.strip().upper()]
    if year is not None:
        sql += " AND year = ?"
        params.append(year)
    return _read(sql + " ORDER BY year", tuple(params))


@st.cache_data(ttl=600)
def get_all_ratios() -> pd.DataFrame:
    """Full financial_ratios table for portfolio-level analytics."""
    return _read("SELECT * FROM financial_ratios")


@st.cache_data(ttl=600)
def get_pl(ticker: str) -> pd.DataFrame:
    """Annual profit & loss history for one company."""
    return _read(
        "SELECT * FROM profitandloss WHERE company_id = ? ORDER BY year",
        (ticker.strip().upper(),),
    )


@st.cache_data(ttl=600)
def get_all_pl() -> pd.DataFrame:
    """Company, year, sales and net profit for every P&L row."""
    return _read(
        "SELECT company_id, year, sales, net_profit FROM profitandloss"
    )


@st.cache_data(ttl=600)
def get_bs(ticker: str) -> pd.DataFrame:
    """Annual balance sheet history for one company."""
    return _read(
        "SELECT * FROM balancesheet WHERE company_id = ? ORDER BY year",
        (ticker.strip().upper(),),
    )


@st.cache_data(ttl=600)
def get_cf(ticker: str) -> pd.DataFrame:
    """Annual cash flow history for one company."""
    return _read(
        "SELECT * FROM cashflow WHERE company_id = ? ORDER BY year",
        (ticker.strip().upper(),),
    )


@st.cache_data(ttl=600)
def get_sectors() -> pd.DataFrame:
    """Full sector mapping table."""
    return _read("SELECT * FROM sectors ORDER BY broad_sector, company_id")


@st.cache_data(ttl=600)
def get_peers(group_name: Optional[str] = None) -> pd.DataFrame:
    """Peer group members; all groups when group_name is None."""
    if group_name is None:
        return _read(
            "SELECT * FROM peer_groups ORDER BY peer_group_name, company_id"
        )
    return _read(
        "SELECT * FROM peer_groups WHERE peer_group_name = ? ORDER BY company_id",
        (group_name,),
    )


@st.cache_data(ttl=600)
def get_valuation(ticker: str) -> pd.DataFrame:
    """Historical valuation multiples (2019-2024) for one company."""
    return _read(
        "SELECT * FROM market_cap WHERE company_id = ? ORDER BY year",
        (ticker.strip().upper(),),
    )


@st.cache_data(ttl=600)
def get_market_caps() -> pd.DataFrame:
    """Full market_cap table (2019-2024 valuation multiples)."""
    return _read("SELECT * FROM market_cap ORDER BY company_id, year")


@st.cache_data(ttl=600)
def get_pros_cons(ticker: str) -> pd.DataFrame:
    """Qualitative pros and cons notes for one company."""
    return _read(
        "SELECT * FROM prosandcons WHERE company_id = ? ORDER BY id",
        (ticker.strip().upper(),),
    )


@st.cache_data(ttl=600)
def get_capital_allocation() -> pd.DataFrame:
    """Capital allocation patterns per company-year; derived if table absent."""
    try:
        return _read("SELECT * FROM capital_allocation")
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        cf = _read(
            """
            SELECT company_id, year, operating_activity, investing_activity,
                   financing_activity
            FROM cashflow
            """
        )
        signs = cf[
            ["operating_activity", "investing_activity", "financing_activity"]
        ].fillna(0).map(lambda v: "+" if v >= 0 else "-")
        cf[["CFO_sign", "CFI_sign", "CFF_sign"]] = signs
        cf["pattern_label"] = signs.apply(tuple, axis=1).map(_PATTERNS)
        return cf[
            ["company_id", "year", "CFO_sign", "CFI_sign", "CFF_sign",
             "pattern_label"]
        ]

@st.cache_data(ttl=600)
def get_documents(ticker: str) -> pd.DataFrame:
    """Annual report links for one company, newest first."""
    return _read(
        """
        SELECT Year, Annual_Report
        FROM documents
        WHERE company_id = ?
        ORDER BY Year DESC
        """,
        (ticker.strip().upper(),),
    )