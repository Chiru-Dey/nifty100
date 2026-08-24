import logging
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.etl.normaliser import normalize_ticker, normalize_year
from src.etl.validator import ANNUAL_TABLES, validate_all

load_dotenv()

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
SUPP_DIR = Path("data/supporting")
OUTPUT_DIR = Path("output")
DB_PATH = Path(os.getenv("DB_PATH", "data/nifty100.db"))
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
CORE_FILES = (
    "companies",
    "profitandloss",
    "balancesheet",
    "cashflow",
    "analysis",
    "documents",
    "prosandcons",
)
SUPP_FILES = (
    "sectors",
    "stock_prices",
    "market_cap",
    "financial_ratios",
    "peer_groups",
)
YEAR_TABLES = ANNUAL_TABLES + ("financial_ratios",)
DROP_ID_TABLES = (
    "sectors",
    "stock_prices",
    "market_cap",
    "financial_ratios",
    "peer_groups",
)
DEDUP_KEYS = {
    "profitandloss": ["company_id", "year"],
    "balancesheet": ["company_id", "year"],
    "cashflow": ["company_id", "year"],
    "documents": ["company_id", "Year"],
    "market_cap": ["company_id", "year"],
    "financial_ratios": ["company_id", "year"],
    "stock_prices": ["company_id", "date"],
}
PEER_COL_MAP = {
    "peer_group": "peer_group_name",
    "group_name": "peer_group_name",
    "benchmark": "is_benchmark",
    "member": "company_id",
}
AuditBundle = tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, pd.DataFrame]


def load_excel(path: Path, header: int = 1) -> pd.DataFrame:
    """Read one Excel file, returning an empty frame on failure."""
    try:
        return pd.read_excel(path, header=header)
    except Exception:
        logger.exception("unreadable file: %s", path)
        return pd.DataFrame()


def normalise_frame(name: str, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalise ticker/year columns and split out rejected rows."""
    df = df.copy()
    if name in DROP_ID_TABLES and "id" in df.columns:
        df = df.drop(columns="id")
    if name == "peer_groups":
        df = df.rename(columns=PEER_COL_MAP)
    if name == "companies":
        ticker_col = "id"
    elif "company_id" in df.columns:
        ticker_col = "company_id"
    else:
        ticker_col = None
    if ticker_col:
        df[ticker_col] = df[ticker_col].map(normalize_ticker)
    if name == "market_cap" and "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    if "year" in df.columns and name in YEAR_TABLES:
        df["year"] = df["year"].map(normalize_year)
    bad = pd.Series(False, index=df.index)
    if ticker_col:
        bad |= df[ticker_col] == "MISSING"
    if "year" in df.columns and name in YEAR_TABLES:
        bad |= df["year"] == "PARSE_ERROR"
    rejected = df.loc[bad].assign(file=name) if bad.any() else pd.DataFrame()
    return df.loc[~bad], rejected


def clean_frames(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Apply CRITICAL DQ actions: dedup, orphan and length rejection, FA clip."""
    valid = set(frames.get("companies", pd.DataFrame()).get("id", []))
    for name, df in frames.items():
        if df.empty:
            continue
        if "company_id" in df.columns:
            df = df[
                df["company_id"].isin(valid) & df["company_id"].str.len().between(2, 12)
            ]
        elif name == "companies":
            df = df[df["id"].str.len().between(2, 12)]
        if name in DEDUP_KEYS:
            df = df.drop_duplicates(subset=DEDUP_KEYS[name], keep="last")
        if name == "balancesheet" and "fixed_assets" in df.columns:
            df = df.copy()
            df["fixed_assets"] = pd.to_numeric(
                df["fixed_assets"], errors="coerce"
            ).clip(lower=0)
        frames[name] = df
    return frames


def load_all() -> AuditBundle:
    """Load, normalise and validate all 12 datasets with audit stats."""
    frames: dict[str, pd.DataFrame] = {}
    rejects: list[pd.DataFrame] = []
    rows_in: dict[str, int] = {}
    runtimes: dict[str, float] = {}
    sources = [(n, RAW_DIR / f"{n}.xlsx", 1) for n in CORE_FILES]
    sources += [(n, SUPP_DIR / f"{n}.xlsx", 0) for n in SUPP_FILES]
    for name, path, header in sources:
        started = time.perf_counter()
        df, rejected = normalise_frame(name, load_excel(path, header=header))
        runtimes[name] = time.perf_counter() - started
        rows_in[name] = len(df) + len(rejected)
        frames[name] = df
        rejects.append(rejected)
        logger.info(
            "%s: %d rows loaded, %d parse rejections", name, len(df), len(rejected)
        )
    dq_failures = validate_all(frames)
    frames = clean_frames(frames)
    parse_failures = pd.concat(rejects, ignore_index=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    audit = pd.DataFrame(
        {
            "table": list(frames),
            "rows_in": [rows_in[n] for n in frames],
            "rows_out": [len(frames[n]) for n in frames],
            "rejected": [rows_in[n] - len(frames[n]) for n in frames],
            "timestamp": stamp,
            "runtime_s": [round(runtimes[n], 3) for n in frames],
        }
    )
    return frames, parse_failures, dq_failures, audit


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Create the database and apply the schema with FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


def write_frames(conn: sqlite3.Connection, frames: dict[str, pd.DataFrame]) -> None:
    """Replace table contents with the given frames (idempotent load)."""
    for name in reversed(list(frames)):
        conn.execute(f"DELETE FROM {name}")
    for name, df in frames.items():
        df.to_sql(name, conn, if_exists="append", index=False)
    conn.commit()


def main() -> int:
    """CLI entry point for the full 12-file loader."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    frames, parse_failures, dq_failures, audit = load_all()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parse_failures.to_csv(OUTPUT_DIR / "parse_failures.csv", index=False)
    dq_failures.to_csv(OUTPUT_DIR / "validation_failures.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "load_audit.csv", index=False)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db()
    try:
        write_frames(conn, frames)
        fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    finally:
        conn.close()
    critical = int((dq_failures["severity"] == "CRITICAL").sum())
    logger.info(
        "rows: %d | parse rej: %d | dq viol: %d (crit %d) | fk viol: %d",
        sum(len(df) for df in frames.values()),
        len(parse_failures),
        len(dq_failures),
        critical,
        fk_violations,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
