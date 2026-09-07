"""Cash flow intelligence: quality, capex intensity, distress, allocation."""

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))

PATTERN_LABELS = {
    "+-+": "Growth via External Financing",
    "++-": "Divestment & Shareholder Returns",
    "+++": "Liquidity Build",
    "---": "Reserve-Funded Investment & Paydown",
    "-+-": "Asset-Sale Funded Operations",
    "--+": "Distress - Financing the Burn",
    "-++": "Distress - Restructuring & Raising",
}

logger = logging.getLogger(__name__)


def _sign(value: float) -> str:
    """Return '+' for inflows and '-' for zero or outflows."""
    return "+" if value > 0 else "-"


def allocation_label(row: pd.Series) -> str:
    """Map CFO/CFI/CFF sign pattern to capital allocation class."""
    key = (
        _sign(row["operating_activity"])
        + _sign(row["investing_activity"])
        + _sign(row["financing_activity"])
    )
    if key != "+--":
        return PATTERN_LABELS[key]
    delevering = (
        pd.notna(row["borrowings"])
        and pd.notna(row["borrowings_prev"])
        and row["borrowings"] < row["borrowings_prev"]
    )
    return (
        "Reinvestor - Debt Paydown"
        if delevering
        else "Shareholder Returns & Reinvestment"
    )


def cfo_quality_label(score: float | None) -> str:
    """Classify the 5yr average CFO/PAT ratio into a quality band."""
    if score is None:
        return "Insufficient Data"
    if score > 1.0:
        return "High Quality"
    if score >= 0.5:
        return "Moderate"
    return "Accrual Risk"


def capex_label(pct: float | None) -> str:
    """Classify capex intensity percentage into a band."""
    if pct is None:
        return "N/A"
    if pct < 3:
        return "Asset Light"
    if pct <= 8:
        return "Moderate"
    return "Capital Intensive"


def fcf_cagr_5yr(fcf_by_year: dict[str, float], latest_year: str) -> float | None:
    """5yr FCF CAGR with standard sign edge cases applied."""
    start_key = f"{int(latest_year[:4]) - 5}{latest_year[4:]}"
    start, end = fcf_by_year.get(start_key), fcf_by_year.get(latest_year)
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / 5) - 1) * 100


def load_frames(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load and merge cash flow, P&L, balance sheet and sector frames."""
    cf = pd.read_sql(
        "SELECT company_id, year, operating_activity, investing_activity, "
        "financing_activity FROM cashflow",
        conn,
    )
    pl = pd.read_sql(
        "SELECT company_id, year, sales, net_profit, operating_profit "
        "FROM profitandloss",
        conn,
    )
    bs = pd.read_sql("SELECT company_id, year, borrowings FROM balancesheet", conn)
    sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    df = cf.merge(pl, on=["company_id", "year"], how="left")
    df = df.merge(bs, on=["company_id", "year"], how="left")
    df = df.merge(sectors, on="company_id", how="left")
    df = df.sort_values(["company_id", "year"])
    df["fcf_cr"] = df["operating_activity"] + df["investing_activity"]
    df["borrowings_prev"] = df.groupby("company_id")["borrowings"].shift(1)
    for col, src in (
        ("cfo_sign", "operating_activity"),
        ("cfi_sign", "investing_activity"),
        ("cff_sign", "financing_activity"),
    ):
        df[col] = df[src].map(_sign)
    df["pattern_label"] = df.apply(allocation_label, axis=1)
    return df


def company_row(g: pd.DataFrame) -> dict:
    """Compute all Module 7 metrics for a single company."""
    latest = g.iloc[-1]
    window = g.tail(5)
    mask = window["net_profit"] > 0
    ratios = window.loc[mask, "operating_activity"] / window.loc[mask, "net_profit"]
    score = round(float(ratios.mean()), 2) if len(ratios) else None
    sales, cfi = latest["sales"], latest["investing_activity"]
    capex = (
        round(abs(cfi) / sales * 100, 2)
        if pd.notna(sales) and sales > 0 and pd.notna(cfi)
        else None
    )
    op, fcf = latest["operating_profit"], latest["fcf_cr"]
    conversion = (
        round(fcf / op * 100, 2)
        if pd.notna(op) and op > 0 and pd.notna(fcf)
        else None
    )
    fcf_years = {y: v for y, v in zip(g["year"], g["fcf_cr"]) if pd.notna(v)}
    cagr = fcf_cagr_5yr(fcf_years, str(latest["year"]))
    distress = bool(
        latest["operating_activity"] < 0 and latest["financing_activity"] > 0
    )
    delever = bool(
        latest["financing_activity"] < 0
        and pd.notna(latest["borrowings"])
        and pd.notna(latest["borrowings_prev"])
        and latest["borrowings"] < latest["borrowings_prev"]
    )
    return {
        "company_id": latest["company_id"],
        "sector": latest["broad_sector"],
        "cfo_quality_score": score,
        "cfo_quality_label": cfo_quality_label(score),
        "capex_intensity_pct": capex,
        "capex_label": capex_label(capex),
        "fcf_cagr_5yr": None if cagr is None else round(cagr, 2),
        "fcf_conversion_pct": conversion,
        "distress_flag": distress,
        "deleveraging_flag": delever,
        "capital_allocation_label": latest["pattern_label"],
    }


def _empty_row(ticker: str, sector: str | None) -> dict:
    """Placeholder intelligence row for companies without cash flow data."""
    return {
        "company_id": ticker,
        "sector": sector,
        "cfo_quality_score": None,
        "cfo_quality_label": "Insufficient Data",
        "capex_intensity_pct": None,
        "capex_label": "N/A",
        "fcf_cagr_5yr": None,
        "fcf_conversion_pct": None,
        "distress_flag": False,
        "deleveraging_flag": False,
        "capital_allocation_label": "N/A - no cash flow data",
    }


def build_intelligence(df: pd.DataFrame, companies: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cash flow intelligence for every company in the universe."""
    groups = dict(tuple(df.groupby("company_id")))
    sector_map = dict(zip(companies["company_id"], companies["broad_sector"]))
    rows = [
        company_row(groups[ticker])
        if ticker in groups
        else _empty_row(ticker, sector_map.get(ticker))
        for ticker in sorted(companies["company_id"])
    ]
    return pd.DataFrame(rows)


def main() -> None:
    """Write capital allocation, intelligence workbook and distress alerts."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        df = load_frames(conn)
        companies = pd.read_sql(
            "SELECT c.id AS company_id, s.broad_sector FROM companies c "
            "JOIN sectors s ON s.company_id = c.id",
            conn,
        )
    df[
        ["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign", "pattern_label"]
    ].to_csv(OUTPUT_DIR / "capital_allocation.csv", index=False)
    intelligence = build_intelligence(df, companies)
    intelligence.to_excel(OUTPUT_DIR / "cashflow_intelligence.xlsx", index=False)
    flagged = intelligence.loc[intelligence["distress_flag"], "company_id"]
    latest = df.groupby("company_id", sort=True).tail(1).set_index("company_id")
    alerts = latest.loc[
        flagged,
        [
            "broad_sector",
            "year",
            "operating_activity",
            "financing_activity",
            "net_profit",
        ],
    ].reset_index()
    alerts = alerts.rename(
        columns={
            "broad_sector": "sector",
            "operating_activity": "cfo_cr",
            "financing_activity": "cff_cr",
            "net_profit": "net_profit_cr",
        }
    )
    alerts.to_csv(OUTPUT_DIR / "distress_alerts.csv", index=False)
    logger.info(
        "companies=%d distress=%d deleveraging=%d",
        len(intelligence),
        int(intelligence["distress_flag"].sum()),
        int(intelligence["deleveraging_flag"].sum()),
    )


if __name__ == "__main__":
    main()