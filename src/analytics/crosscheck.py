"""ROCE/ROE cross-check and edge case log for the Nifty 100 platform."""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from src.analytics.leverage import compute_leverage
from src.analytics.populate import build_full_frame
from src.analytics.ratios import (
    BASE_DIR,
    DB_PATH,
    check_opm_mismatches,
    load_config,
    load_inputs,
)

logger = logging.getLogger(__name__)

EDGE_LOG_PATH = BASE_DIR / "output" / "ratio_edge_cases.log"
NOTES_PATH = BASE_DIR / "output" / "sector_roce_notes.csv"

ANOMALY_COLUMNS = [
    "company_id",
    "year",
    "metric",
    "computed",
    "source",
    "diff",
    "category",
]


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def configure_edge_logging(path: Path = EDGE_LOG_PATH) -> None:
    """Attach a file handler on the root logger writing ratio_edge_cases.log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    existing = any(
        isinstance(h, logging.FileHandler) and Path(h.baseFilename) == path
        for h in root.handlers
    )
    if not existing:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
        )
        root.addHandler(handler)


def load_snapshot(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Latest-year computed ROCE/ROE joined with source values and sector."""
    with sqlite3.connect(db_path) as conn:
        snapshot = pd.read_sql(
            "SELECT f.company_id, f.year, f.return_on_capital_pct, "
            "f.return_on_equity_pct FROM financial_ratios f "
            "JOIN (SELECT company_id, MAX(year) AS year FROM financial_ratios "
            "GROUP BY company_id) m ON f.company_id = m.company_id "
            "AND f.year = m.year",
            conn,
        )
        companies = pd.read_sql(
            "SELECT id AS company_id, roce_percentage, roe_percentage "
            "FROM companies",
            conn,
        )
        sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    return snapshot.merge(companies, on="company_id").merge(sectors, on="company_id")


def categorise(computed: float, source: float, relative: float) -> str:
    """Categorise an anomaly: data source issue, version difference or formula mismatch."""
    if source <= 0 or (source < 1.0 and computed > 10.0):
        return "data_source_issue"
    if abs(computed - source) / abs(source) <= relative:
        return "version_difference"
    return "formula_mismatch"


def cross_check(snapshot: pd.DataFrame, tolerance: float, relative: float) -> pd.DataFrame:
    """Return ROCE/ROE rows where computed vs source differ beyond tolerance."""
    records = []
    for row in snapshot.itertuples():
        for metric, computed_col, source_col in (
            ("ROCE", "return_on_capital_pct", "roce_percentage"),
            ("ROE", "return_on_equity_pct", "roe_percentage"),
        ):
            computed = _num(getattr(row, computed_col))
            source = _num(getattr(row, source_col))
            if computed is None or source is None:
                continue
            diff = abs(computed - source)
            if diff > tolerance:
                records.append(
                    {
                        "company_id": row.company_id,
                        "year": row.year,
                        "metric": metric,
                        "computed": computed,
                        "source": source,
                        "diff": diff,
                        "category": categorise(computed, source, relative),
                    }
                )
    return pd.DataFrame(records, columns=ANOMALY_COLUMNS)


def verify_financials_suppression(df: pd.DataFrame, config: dict) -> int:
    """Count Financials rows with a raised high-leverage flag; must be zero."""
    frame = compute_leverage(df, config).merge(
        df[["company_id", "broad_sector"]], on="company_id", how="left"
    )
    mask = (frame["broad_sector"] == "Financials") & frame[
        "high_leverage_flag"
    ].astype(bool)
    return int(mask.sum())


def log_debt_free_substitutions(df: pd.DataFrame) -> int:
    """Log debt-free ICR substitutions to the edge case log."""
    count = 0
    for row in df.itertuples():
        if _num(row.interest) == 0:
            count += 1
            logger.info(
                "Debt-free substitution %s %s: ICR displayed as Debt Free",
                row.company_id,
                row.year,
            )
    return count


def write_sector_roce_notes(
    snapshot: pd.DataFrame, anomalies: pd.DataFrame, path: Path = NOTES_PATH
) -> None:
    """Write sector_roce_notes.csv with per-company ROCE cross-check detail."""
    categories = (
        anomalies[anomalies["metric"] == "ROCE"]
        .set_index("company_id")["category"]
    )
    notes = snapshot.copy()
    notes["anomaly_category"] = notes["company_id"].map(categories)
    notes["roce_anomaly"] = notes["anomaly_category"].notna()
    path.parent.mkdir(parents=True, exist_ok=True)
    notes.to_csv(path, index=False)


def main() -> None:
    """Run Day 13 cross-checks, suppression verification and edge case log."""
    logging.basicConfig(level=logging.INFO)
    configure_edge_logging()
    config = load_config()
    merged = load_inputs()
    build_full_frame(merged, config)
    check_opm_mismatches(merged, config["opm_tolerance_pct"])
    log_debt_free_substitutions(merged)
    snapshot = load_snapshot()
    anomalies = cross_check(
        snapshot, config["roce_roe_tolerance_pct"], config["version_diff_relative"]
    )
    for a in anomalies.itertuples():
        logger.warning(
            "Cross-check anomaly %s %s %s computed=%.2f source=%.2f diff=%.2f category=%s",
            a.company_id,
            a.year,
            a.metric,
            a.computed,
            a.source,
            a.diff,
            a.category,
        )
    write_sector_roce_notes(snapshot, anomalies)
    violations = verify_financials_suppression(merged, config)
    if violations:
        logger.error("Financials D/E suppression violated: %d rows", violations)
    else:
        logger.info("Financials D/E suppression verified across all 19 companies")
    logger.info(
        "Edge log: %s; %d anomalies categorised", EDGE_LOG_PATH.name, len(anomalies)
    )


if __name__ == "__main__":
    main()