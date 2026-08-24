"""Profitability ratio engine for the Nifty 100 platform."""

import logging
import sqlite3
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = BASE_DIR / "data" / "nifty100.db"
CONFIG_PATH = BASE_DIR / "config" / "sector_benchmarks.yaml"

RATIO_COLUMNS = {
    "net_profit_margin_pct": "REAL",
    "operating_profit_margin_pct": "REAL",
    "return_on_equity_pct": "REAL",
    "return_on_capital_pct": "REAL",
    "return_on_assets_pct": "REAL",
    "roce_rating": "TEXT",
}


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def ebit(operating_profit: float | None, depreciation: float | None) -> float | None:
    """EBIT = operating profit less depreciation."""
    op = _num(operating_profit)
    if op is None:
        return None
    return op - (_num(depreciation) or 0.0)


def net_profit_margin(net_profit: float | None, sales: float | None) -> float | None:
    """Net profit margin percent; None when sales is zero or missing."""
    profit = _num(net_profit)
    revenue = _num(sales)
    if profit is None or revenue in (None, 0):
        return None
    return profit / revenue * 100


def operating_profit_margin(
    operating_profit: float | None, sales: float | None
) -> float | None:
    """Operating profit margin percent; None when sales is zero or missing."""
    op = _num(operating_profit)
    revenue = _num(sales)
    if op is None or revenue in (None, 0):
        return None
    return op / revenue * 100


def return_on_equity(
    net_profit: float | None,
    equity_capital: float | None,
    reserves: float | None,
) -> float | None:
    """ROE percent; None when total equity is zero or negative."""
    profit = _num(net_profit)
    equity = _num(equity_capital)
    if profit is None or equity is None:
        return None
    total = equity + (_num(reserves) or 0.0)
    if total <= 0:
        return None
    return profit / total * 100


def return_on_capital(
    ebit_value: float | None,
    equity_capital: float | None,
    reserves: float | None,
    borrowings: float | None,
) -> float | None:
    """ROCE percent; None when capital employed is zero or negative."""
    ebit_ = _num(ebit_value)
    equity = _num(equity_capital)
    if ebit_ is None or equity is None:
        return None
    capital = equity + (_num(reserves) or 0.0) + (_num(borrowings) or 0.0)
    if capital <= 0:
        return None
    return ebit_ / capital * 100


def return_on_assets(
    net_profit: float | None, total_assets: float | None
) -> float | None:
    """ROA percent; None when total assets is zero or missing."""
    profit = _num(net_profit)
    assets = _num(total_assets)
    if profit is None or assets in (None, 0):
        return None
    return profit / assets * 100


def rate_roce(roce: float | None, sector: str | None, benchmarks: dict) -> str | None:
    """Rate ROCE against sector-relative config thresholds."""
    if roce is None:
        return None
    thresholds = benchmarks.get(sector or "", benchmarks["default"])
    if roce >= thresholds["excellent"]:
        return "excellent"
    if roce >= thresholds["good"]:
        return "good"
    return "below_benchmark"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load ratio tolerances and benchmarks from YAML."""
    with path.open() as fh:
        return yaml.safe_load(fh)


def load_inputs(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Join P&L, balance sheet, cash flow, sector and company rows."""
    with sqlite3.connect(db_path) as conn:
        pl = pd.read_sql(
            "SELECT company_id, year, sales, operating_profit, opm_percentage, "
            "depreciation, other_income, interest, net_profit, eps, "
            "dividend_payout FROM profitandloss",
            conn,
        )
        bs = pd.read_sql(
            "SELECT company_id, year, equity_capital, reserves, borrowings, "
            "investments, total_assets FROM balancesheet",
            conn,
        )
        cf = pd.read_sql(
            "SELECT company_id, year, operating_activity, investing_activity, "
            "financing_activity FROM cashflow",
            conn,
        )
        sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
        companies = pd.read_sql(
            "SELECT id AS company_id, face_value FROM companies", conn
        )
    return (
        pl.merge(bs, on=["company_id", "year"])
        .merge(cf, on=["company_id", "year"], how="left")
        .merge(sectors, on="company_id", how="left")
        .merge(companies, on="company_id", how="left")
    )

def check_opm_mismatches(df: pd.DataFrame, tolerance: float) -> int:
    """Log DQ-05 warnings where computed OPM deviates beyond tolerance."""
    mismatches = 0
    for row in df.itertuples():
        computed = operating_profit_margin(row.operating_profit, row.sales)
        reported = _num(row.opm_percentage)
        if computed is None or reported is None:
            continue
        if abs(computed - reported) > tolerance:
            mismatches += 1
            logger.warning(
                "DQ-05 OPM mismatch %s %s computed=%.2f reported=%.2f",
                row.company_id,
                row.year,
                computed,
                reported,
            )
    return mismatches


def compute_profitability(df: pd.DataFrame, benchmarks: dict) -> pd.DataFrame:
    """Compute profitability KPIs for every company-year row."""
    out = df[["company_id", "year"]].copy()
    out["net_profit_margin_pct"] = df.apply(
        lambda r: net_profit_margin(r.net_profit, r.sales), axis=1
    )
    out["operating_profit_margin_pct"] = df.apply(
        lambda r: operating_profit_margin(r.operating_profit, r.sales), axis=1
    )
    out["return_on_equity_pct"] = df.apply(
        lambda r: return_on_equity(r.net_profit, r.equity_capital, r.reserves), axis=1
    )
    out["return_on_capital_pct"] = df.apply(
        lambda r: return_on_capital(
            ebit(r.operating_profit, r.depreciation),
            r.equity_capital,
            r.reserves,
            r.borrowings,
        ),
        axis=1,
    )
    out["return_on_assets_pct"] = df.apply(
        lambda r: return_on_assets(r.net_profit, r.total_assets), axis=1
    )
    out["roce_rating"] = [
        rate_roce(v, s, benchmarks)
        for v, s in zip(out["return_on_capital_pct"], df["broad_sector"])
    ]
    return out


def save_ratios(
    frame: pd.DataFrame,
    columns: dict | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Upsert ratio columns into financial_ratios idempotently."""
    columns = RATIO_COLUMNS if columns is None else columns
    keys = list(frame[["company_id", "year"]].itertuples(index=False, name=None))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS financial_ratios ("
            "company_id TEXT NOT NULL, year TEXT NOT NULL, "
            "PRIMARY KEY (company_id, year))"
        )
        existing = {i[1] for i in conn.execute("PRAGMA table_info(financial_ratios)")}
        for column, dtype in columns.items():
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE financial_ratios ADD COLUMN {column} {dtype}"
                )
        conn.executemany(
            "INSERT OR IGNORE INTO financial_ratios (company_id, year) VALUES (?, ?)",
            keys,
        )
        for column in columns:
            conn.executemany(
                f"UPDATE financial_ratios SET {column} = ? "
                "WHERE company_id = ? AND year = ?",
                [
                    (None if pd.isna(v) else v, c, y)
                    for v, (c, y) in zip(frame[column], keys)
                ],
            )


def main() -> None:
    """Run the Day 8 profitability ratio pipeline."""
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    merged = load_inputs()
    mismatches = check_opm_mismatches(merged, config["opm_tolerance_pct"])
    frame = compute_profitability(merged, config["roce_benchmarks"])
    save_ratios(frame)
    logger.info("Computed %d rows; %d OPM mismatches", len(frame), mismatches)


if __name__ == "__main__":
    main()