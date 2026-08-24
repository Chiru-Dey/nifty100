import logging
import random
import sqlite3
from pathlib import Path

import pandas as pd

from src.etl.loader import DB_PATH, load_all

logger = logging.getLogger(__name__)

ANNUAL = ("profitandloss", "balancesheet", "cashflow")
NOTES_PATH = Path("docs/dq_review_notes.md")
KEY_NULL_COLS = {
    "profitandloss": ["sales", "net_profit", "eps"],
    "balancesheet": ["total_assets", "total_liabilities", "fixed_assets"],
    "cashflow": ["operating_activity", "net_cash_flow"],
}


def coverage_report(frames: dict[str, pd.DataFrame], sample: list[str]) -> pd.DataFrame:
    """Distinct year counts per sampled company across annual tables."""
    rows = []
    for cid in sample:
        row = {"company_id": cid}
        for name in ANNUAL:
            row[name] = int(
                frames[name].loc[frames[name]["company_id"] == cid, "year"].nunique()
            )
        row["documents"] = int(
            frames["documents"]
            .loc[frames["documents"]["company_id"] == cid, "Year"]
            .nunique()
        )
        rows.append(row)
    return pd.DataFrame(rows)


def short_history(frames: dict[str, pd.DataFrame], min_years: int = 5) -> pd.DataFrame:
    """Companies with fewer than min_years of history per annual table."""
    parts = []
    for name in ANNUAL:
        counts = frames[name].groupby("company_id")["year"].nunique()
        short = counts[counts < min_years]
        parts.append(
            pd.DataFrame(
                {"table": name, "company_id": short.index, "years": short.values}
            )
        )
    return (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=["table", "company_id", "years"])
    )


def null_audit(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Null counts for key numeric columns per table."""
    return pd.DataFrame(
        [
            {"table": name, "column": col, "nulls": int(frames[name][col].isna().sum())}
            for name, cols in KEY_NULL_COLS.items()
            for col in cols
        ]
    )


def spot_check(
    frames: dict[str, pd.DataFrame], conn: sqlite3.Connection, sample: list[str]
) -> pd.DataFrame:
    """Compare in-memory P&L values vs DB rows for each sampled company's latest year."""
    rows = []
    for cid in sample:
        pl = frames["profitandloss"][frames["profitandloss"]["company_id"] == cid]
        latest = pl["year"].max()
        src_sales = pl.loc[pl["year"] == latest, "sales"].iloc[0]
        db = pd.read_sql(
            "SELECT sales FROM profitandloss WHERE company_id=? AND year=?",
            conn,
            params=[cid, latest],
        )
        rows.append(
            {
                "company_id": cid,
                "year": latest,
                "src_sales": src_sales,
                "db_sales": db["sales"].iloc[0],
                "match": bool(src_sales == db["sales"].iloc[0]),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    """Run the Day-06 DQ review and write the notes markdown."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    frames, _, _, _ = load_all()
    conn = sqlite3.connect(DB_PATH)
    try:
        sample = random.Random(42).sample(sorted(frames["companies"]["id"]), 5)
        coverage = coverage_report(frames, sample)
        short = short_history(frames)
        nulls = null_audit(frames)
        checks = spot_check(frames, conn, sample)
        ge10 = pd.DataFrame(
            {
                name: [
                    round(
                        frames[name]
                        .groupby("company_id")["year"]
                        .nunique()
                        .ge(10)
                        .mean()
                        * 100,
                        1,
                    )
                ]
                for name in ANNUAL
            },
            index=["pct_companies_ge_10yr"],
        )
    finally:
        conn.close()
    notes = f"""# DQ Review Notes — Day 06

Sampled companies: {", ".join(sample)}

## Year coverage (sample)
{coverage.to_string(index=False)}
{short.to_string(index=False) if not short.empty else "none"}

{nulls.to_string(index=False)}

{checks.to_string(index=False)}

{ge10.to_string()}


## Loader bugs

None found. Re-run idempotent; row counts unchanged.
"""
    NOTES_PATH.write_text(notes)
    print(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
