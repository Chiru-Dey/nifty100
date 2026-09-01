from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.peer import DB_PATH
from src.screener.engine import load_config, load_financial_ratios, run_all_presets

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
PEER_XLSX = BASE_DIR / "output" / "peer_comparison.xlsx"
PRESET_BAND = (5, 50)


def check_preset_bands(results: dict[str, pd.DataFrame]) -> bool:
    return all(PRESET_BAND[0] <= len(r) <= PRESET_BAND[1] for r in results.values())


def check_quality_thresholds(quality: pd.DataFrame) -> bool:
    print(quality[["company_id", "return_on_equity_pct", "debt_to_equity"]].head(5).to_string(index=False))
    return bool((quality["return_on_equity_pct"] >= 15).all() and (quality["debt_to_equity"] <= 1).all())


def check_peer_ranking(group: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        pp = pd.read_sql_query("SELECT * FROM peer_percentiles WHERE peer_group_name = ?", conn, params=(group,))
    roe = pp[pp["metric"] == "ROE"]
    if roe.empty:
        return False
    return bool(roe.loc[roe["value"].idxmax(), "company_id"] == roe.loc[roe["percentile_rank"].idxmax(), "company_id"])


def check_peer_sheets() -> bool:
    xl = pd.ExcelFile(PEER_XLSX)
    return len(xl.sheet_names) == 11


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    results = run_all_presets(load_financial_ratios(), load_config())
    checks = {
        "preset bands 5-50": check_preset_bands(results),
        "quality compounder thresholds": check_quality_thresholds(results["quality_compounder"]),
        "IT Services ROE ranking": check_peer_ranking("IT Services"),
        "FMCG ROE ranking": check_peer_ranking("FMCG"),
        "peer_comparison 11 sheets": check_peer_sheets(),
    }
    for name, ok in checks.items():
        logger.info("%-32s %s", name, "PASS" if ok else "FAIL")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())