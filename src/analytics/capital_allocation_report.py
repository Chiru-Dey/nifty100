"""Capital allocation coverage check, distribution and pattern change report."""

import logging
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))
ALLOCATION_PATH = OUTPUT_DIR / "capital_allocation.csv"
INTELLIGENCE_PATH = OUTPUT_DIR / "cashflow_intelligence.xlsx"
DISTRIBUTION_PATH = OUTPUT_DIR / "pattern_distribution.csv"
CHANGES_PATH = OUTPUT_DIR / "pattern_changes.csv"

CANONICAL_LABELS = {
    "+--": "Reinvestor / Shareholder Returns",
    "+-+": "Growth via External Financing",
    "++-": "Divestment & Shareholder Returns",
    "+++": "Liquidity Build",
    "---": "Reserve-Funded Investment & Paydown",
    "-+-": "Asset-Sale Funded Operations",
    "--+": "Distress - Financing the Burn",
    "-++": "Distress - Restructuring & Raising",
}

logger = logging.getLogger(__name__)


def load_allocation() -> pd.DataFrame:
    """Load capital_allocation.csv with the sign pattern key derived."""
    df = pd.read_csv(ALLOCATION_PATH, dtype={"company_id": str, "year": str})
    df["pattern_signs"] = df["cfo_sign"] + df["cfi_sign"] + df["cff_sign"]
    return df.sort_values(["company_id", "year"])


def verify_coverage(
    df: pd.DataFrame, conn: sqlite3.Connection
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """Classify gaps: csv vs cashflow keys, plus companies lacking cashflow."""
    expected = pd.read_sql("SELECT company_id, year FROM cashflow", conn)
    expected["year"] = expected["year"].astype(str)
    actual = df[["company_id", "year"]].drop_duplicates()
    merged = expected.merge(
        actual, on=["company_id", "year"], how="outer", indicator=True
    )
    missing = merged.loc[merged["_merge"] == "left_only", ["company_id", "year"]]
    extra = merged.loc[merged["_merge"] == "right_only", ["company_id", "year"]]
    companies = pd.read_sql("SELECT id AS company_id FROM companies", conn)
    source_gap = sorted(set(companies["company_id"]) - set(expected["company_id"]))
    return (
        list(missing.itertuples(index=False, name=None)),
        list(extra.itertuples(index=False, name=None)),
        source_gap,
    )



def latest_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Return the most recent pattern row per company."""
    return df.groupby("company_id", sort=True).tail(1)


def pattern_distribution(latest: pd.DataFrame) -> pd.DataFrame:
    """Count companies per sign pattern at each company's latest year."""
    counts = (
        latest.groupby("pattern_signs")
        .size()
        .reindex(list(CANONICAL_LABELS), fill_value=0)
        .reset_index()
    )
    counts.columns = ["pattern_signs", "company_count"]
    counts["pattern_label"] = counts["pattern_signs"].map(CANONICAL_LABELS)
    return counts[["pattern_signs", "pattern_label", "company_count"]]


def pattern_changes(df: pd.DataFrame) -> pd.DataFrame:
    """Return year-over-year sign pattern transitions per company."""
    records = []
    for ticker, g in df.groupby("company_id", sort=True):
        prev = g.iloc[:-1].reset_index(drop=True)
        curr = g.iloc[1:].reset_index(drop=True)
        for i in range(len(prev)):
            if prev.loc[i, "pattern_signs"] == curr.loc[i, "pattern_signs"]:
                continue
            frm, to = prev.loc[i], curr.loc[i]
            desc = (
                f"{ticker} moved from {frm['pattern_label']} to "
                f"{to['pattern_label']} ({frm['year']} -> {to['year']})"
            )
            records.append(
                (
                    ticker,
                    frm["year"],
                    to["year"],
                    frm["pattern_label"],
                    to["pattern_label"],
                    desc,
                )
            )
    return pd.DataFrame(
        records,
        columns=[
            "company_id",
            "from_year",
            "to_year",
            "from_pattern",
            "to_pattern",
            "description",
        ],
    )


def ensure_intelligence_column(latest: pd.DataFrame) -> None:
    """Add or refresh the capital allocation label in the intelligence xlsx."""
    if not INTELLIGENCE_PATH.exists():
        logger.error("cashflow_intelligence.xlsx missing - run cashflow_kpis.py")
        return
    xl = pd.read_excel(INTELLIGENCE_PATH)
    labels = latest.set_index("company_id")["pattern_label"]
    xl["capital_allocation_label"] = xl["company_id"].map(labels)
    xl.to_excel(INTELLIGENCE_PATH, index=False)
    logger.info("capital_allocation_label refreshed in cashflow_intelligence.xlsx")



def main() -> int:
    """Verify coverage, write distribution and pattern change reports."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    if not ALLOCATION_PATH.exists():
        logger.error("capital_allocation.csv missing - run cashflow_kpis.py first")
        return 1
    df = load_allocation()
    with sqlite3.connect(DB_PATH) as conn:
        missing, extra, source_gap = verify_coverage(df, conn)
    if missing:
        logger.error("capital_allocation.csv missing %d company-years", len(missing))
        return 1
    if extra:
        logger.warning("%d stale company-year rows beyond cashflow table", len(extra))
    if source_gap:
        logger.warning(
            "DQ-16 source gap - no cashflow records for: %s", ", ".join(source_gap)
        )
        pd.DataFrame(
            {"company_id": source_gap, "issue": "no cashflow records in source"}
        ).to_csv(OUTPUT_DIR / "coverage_gaps.csv", index=False)
    logger.info(
        "coverage verified: %d/%d companies, %d company-year rows",
        df["company_id"].nunique(),
        df["company_id"].nunique() + len(source_gap),
        len(df),
    )
    latest = latest_patterns(df)
    dist = pattern_distribution(latest)
    dist.to_csv(DISTRIBUTION_PATH, index=False)
    for row in dist.itertuples(index=False):
        logger.info(
            "%s | %s | %d", row.pattern_signs, row.pattern_label, row.company_count
        )
    ensure_intelligence_column(latest)
    changes = pattern_changes(df)
    changes.to_csv(CHANGES_PATH, index=False)
    logger.info("year-over-year pattern changes recorded: %d", len(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())