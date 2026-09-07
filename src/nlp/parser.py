"""NLP parser for analysis.xlsx growth text fields."""

import logging
import os
import re
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
ANALYSIS_PATH = Path(
    os.getenv("ANALYSIS_XLSX", BASE_DIR / "data" / "raw" / "analysis.xlsx")
)
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))

PATTERN = re.compile(r"(\d+)\s*Years?:?\s*([\d.]+)%")
TEXT_FIELDS = (
    "compounded_sales_growth",
    "compounded_profit_growth",
    "stock_price_cagr",
    "roe",
)
CAGR_PREFIX = {
    "compounded_sales_growth": "revenue_cagr",
    "compounded_profit_growth": "pat_cagr",
}
DIVERGENCE_THRESHOLD = float(os.getenv("CAGR_DIVERGENCE_PCT", "5.0"))

logger = logging.getLogger(__name__)


def load_analysis(path: Path) -> pd.DataFrame:
    """Load analysis.xlsx (header=1) with normalised tickers."""
    df = pd.read_excel(path, header=1)
    df["company_id"] = df["company_id"].astype(str).str.strip().str.upper()
    return df


def parse_text(text: object) -> tuple[int, float] | None:
    """Extract (period_years, value_pct) from strings like '10 Years: 21%'."""
    if not isinstance(text, str):
        return None
    match = PATTERN.search(text)
    return (int(match.group(1)), float(match.group(2))) if match else None


def parse_analysis(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse target fields into (parsed, failures) frames."""
    parsed, failures = [], []
    for row in df.itertuples(index=False):
        for field in TEXT_FIELDS:
            raw = getattr(row, field, None)
            result = parse_text(raw)
            if result is None:
                failures.append((row.company_id, field, raw))
            else:
                parsed.append((row.company_id, field, *result))
    parsed_df = pd.DataFrame(
        parsed, columns=["company_id", "metric_type", "period_years", "value_pct"]
    )
    failures_df = pd.DataFrame(
        failures, columns=["company_id", "metric_type", "raw_value"]
    )
    return parsed_df, failures_df


def _ratio_cagr(
    conn: sqlite3.Connection, columns: set[str], ticker: str, prefix: str, period: int
) -> float | None:
    """Fetch latest precomputed CAGR for 3/5/10yr windows."""
    col = f"{prefix}_{period}yr"
    if period not in (3, 5, 10) or col not in columns:
        return None
    row = conn.execute(
        f"SELECT {col} FROM financial_ratios "
        "WHERE company_id = ? ORDER BY year DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row[0] if row else None


def _avg_roe(conn: sqlite3.Connection, ticker: str, period: int) -> float | None:
    """Average ROE over the latest period years."""
    row = conn.execute(
        "SELECT AVG(return_on_equity_pct) FROM ("
        "SELECT return_on_equity_pct FROM financial_ratios "
        "WHERE company_id = ? AND return_on_equity_pct IS NOT NULL "
        "ORDER BY year DESC LIMIT ?)",
        (ticker, period),
    ).fetchone()
    return row[0] if row else None


def _market_cap_cagr(
    conn: sqlite3.Connection, ticker: str, period: int
) -> float | None:
    """CAGR of market_cap_crore over the period ending at the latest year."""
    rows = conn.execute(
        "SELECT year, market_cap_crore FROM market_cap "
        "WHERE company_id = ? AND market_cap_crore > 0 ORDER BY year",
        (ticker,),
    ).fetchall()
    if not rows or period <= 0:
        return None
    caps = {year: cap for year, cap in rows}
    end_year = rows[-1][0]
    start, end = caps.get(end_year - period), caps.get(end_year)
    if not start or not end:
        return None
    return ((end / start) ** (1 / period) - 1) * 100


def computed_value(
    conn: sqlite3.Connection,
    columns: set[str],
    ticker: str,
    metric_type: str,
    period: int,
) -> float | None:
    """Resolve the computed counterpart for a parsed metric."""
    if metric_type in CAGR_PREFIX:
        return _ratio_cagr(conn, columns, ticker, CAGR_PREFIX[metric_type], period)
    if metric_type == "roe":
        return _avg_roe(conn, ticker, period)
    if metric_type == "stock_price_cagr":
        return _market_cap_cagr(conn, ticker, period)
    return None


def cross_validate(parsed: pd.DataFrame) -> pd.DataFrame:
    """Compare parsed values vs computed; flag divergence > threshold."""
    records = []
    with sqlite3.connect(DB_PATH) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(financial_ratios)")}
        for row in parsed.itertuples(index=False):
            computed = computed_value(
                conn, columns, row.company_id, row.metric_type, row.period_years
            )
            divergence = None if computed is None else abs(row.value_pct - computed)
            if computed is None:
                status = "NO_COMPUTED"
            else:
                status = "REVIEW" if divergence > DIVERGENCE_THRESHOLD else "OK"
            records.append(
                (
                    row.company_id,
                    row.metric_type,
                    row.period_years,
                    row.value_pct,
                    None if computed is None else round(computed, 2),
                    None if divergence is None else round(divergence, 2),
                    status,
                )
            )
    return pd.DataFrame(
        records,
        columns=[
            "company_id",
            "metric_type",
            "period_years",
            "parsed_pct",
            "computed_pct",
            "divergence_pct",
            "status",
        ],
    )


def main() -> None:
    """Parse analysis.xlsx, write outputs, log summary counts."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed, failures = parse_analysis(load_analysis(ANALYSIS_PATH))
    parsed.to_csv(OUTPUT_DIR / "analysis_parsed.csv", index=False)
    failures.to_csv(OUTPUT_DIR / "parse_failures.csv", index=False)
    cross = cross_validate(parsed)
    cross.to_csv(OUTPUT_DIR / "cross_validation.csv", index=False)
    logger.info(
        "parsed=%d failures=%d flagged=%d",
        len(parsed),
        len(failures),
        int((cross["status"] == "REVIEW").sum()),
    )


if __name__ == "__main__":
    main()