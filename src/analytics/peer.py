from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
PEER_XLSX = BASE_DIR / "data" / "supporting" / "peer_groups.xlsx"
DEBT_FREE_LABEL = "Debt Free"
NO_PEER_GROUP = "No peer group assigned"

METRIC_COLUMNS: dict[str, tuple[str, bool]] = {
    "ROE": ("return_on_equity_pct", True),
    "ROCE": ("return_on_capital_pct", True),
    "Net Profit Margin": ("net_profit_margin_pct", True),
    "D/E": ("debt_to_equity", False),
    "FCF": ("free_cash_flow_cr", True),
    "PAT CAGR 5yr": ("pat_cagr_5yr", True),
    "Revenue CAGR 5yr": ("revenue_cagr_5yr", True),
    "EPS CAGR 5yr": ("eps_cagr_5yr", True),
    "Interest Coverage": ("interest_coverage", True),
    "Asset Turnover": ("asset_turnover", True),
}

OUTPUT_COLUMNS = ["company_id", "peer_group_name", "metric", "value", "percentile_rank", "year"]


def load_peer_groups(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    """Load peer group membership from SQLite, falling back to the xlsx."""
    try:
        with sqlite3.connect(db_path) as conn:
            groups = pd.read_sql_query("SELECT * FROM peer_groups", conn)
    except sqlite3.Error:
        groups = pd.read_excel(PEER_XLSX)
    groups.columns = [str(c).strip().lower() for c in groups.columns]
    group_col = next((c for c in groups.columns if "group" in c), None)
    if group_col and group_col != "peer_group_name":
        groups = groups.rename(columns={group_col: "peer_group_name"})
    groups["company_id"] = groups["company_id"].astype(str).str.strip().str.upper()
    return groups


def load_ratios(db_path: str | Path = DB_PATH) -> pd.DataFrame:
    """Load the financial_ratios table."""
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM financial_ratios", conn)


def _coerce(frame: pd.DataFrame, column: str) -> pd.Series:
    series = frame[column]
    if column == "interest_coverage":
        series = pd.to_numeric(series.replace(DEBT_FREE_LABEL, float("inf")), errors="coerce")
        return series.fillna(float("inf"))
    return pd.to_numeric(series, errors="coerce")


def _percent_rank(series: pd.Series, higher_better: bool) -> pd.Series:
    """SQL-style PERCENT_RANK within the group; inverted when lower is better."""
    if len(series) < 2:
        return pd.Series(0.0, index=series.index)
    ranks = series.rank(method="min", na_option="bottom")
    pr = (ranks - 1) / (len(series) - 1)
    return (1.0 - pr) if not higher_better else pr


def compute_peer_percentiles(groups: pd.DataFrame, ratios: pd.DataFrame) -> pd.DataFrame:
    """PERCENT_RANK for 10 metrics within each of the 11 peer groups."""
    latest = ratios.sort_values(["company_id", "year"]).groupby("company_id", group_keys=False).tail(1)
    merged = groups.merge(latest, on="company_id", how="inner")
    blocks: list[pd.DataFrame] = []
    for group, frame in merged.groupby("peer_group_name"):
        for metric, (column, higher_better) in METRIC_COLUMNS.items():
            if column not in frame.columns:
                logger.warning("Metric %s skipped: missing column %s", metric, column)
                continue
            value = _coerce(frame, column)
            blocks.append(pd.DataFrame({
                "company_id": frame["company_id"].to_numpy(),
                "peer_group_name": group,
                "metric": metric,
                "value": value.round(2).to_numpy(),
                "percentile_rank": _percent_rank(value, higher_better).round(4).to_numpy(),
                "year": frame["year"].to_numpy(),
            }))
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame(columns=OUTPUT_COLUMNS)


def save_peer_percentiles(percentiles: pd.DataFrame, db_path: str | Path = DB_PATH) -> None:
    """Write the peer_percentiles table to SQLite."""
    with sqlite3.connect(db_path) as conn:
        percentiles.to_sql("peer_percentiles", conn, index=False, if_exists="replace")


def get_peer_percentiles(ticker: str, db_path: str | Path = DB_PATH) -> pd.DataFrame | str:
    """Percentile ranks for a ticker, or the no-peer-group message."""
    ticker = ticker.strip().upper()
    with sqlite3.connect(db_path) as conn:
        members = pd.read_sql_query("SELECT DISTINCT company_id FROM peer_groups", conn)
        frame = pd.read_sql_query(
            "SELECT * FROM peer_percentiles WHERE company_id = ?", conn, params=(ticker,)
        )
    if ticker not in set(members["company_id"]):
        logger.info("%s: %s", ticker, NO_PEER_GROUP)
        return NO_PEER_GROUP
    return frame



def main() -> None:
    """Compute peer percentiles for all groups and populate SQLite."""
    logging.basicConfig(level=logging.INFO)
    groups = load_peer_groups()
    percentiles = compute_peer_percentiles(groups, load_ratios())
    save_peer_percentiles(percentiles)
    logger.info(
        "peer_percentiles: %d rows across %d groups",
        len(percentiles), percentiles["peer_group_name"].nunique(),
    )
    with sqlite3.connect(DB_PATH) as conn:
        universe = pd.read_sql_query("SELECT id FROM companies", conn)["id"]
    uncovered = set(universe) - set(groups["company_id"])
    if uncovered:
        logger.info("%d companies -> '%s'", len(uncovered), NO_PEER_GROUP)


if __name__ == "__main__":
    main()