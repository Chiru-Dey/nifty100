import logging
import os
import sqlite3

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
PE_CAUTION_MULT = float(os.getenv("PE_CAUTION_MULT", "1.5"))
PE_DISCOUNT_MULT = float(os.getenv("PE_DISCOUNT_MULT", "0.7"))

SUMMARY_COLUMNS = [
    "company_id", "company_name", "sector", "P/E", "P/B", "EV/EBITDA",
    "FCF_yield_pct", "5yr_median_PE", "PE_vs_sector_median_pct", "flag",
]
FLAG_COLUMNS = [
    "company_id", "company_name", "sector", "P/E", "sector_median_pe",
    "PE_vs_sector_median_pct", "flag", "rationale",
]


def _read(sql: str) -> pd.DataFrame:
    """Run a read-only query against the project SQLite database."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(sql, conn)


def flag_company(pe: float, sector_median: float) -> tuple[str, str]:
    """Return (flag, rationale) per Module 6.6 overvaluation rules."""
    if pd.isna(pe) or pd.isna(sector_median) or sector_median <= 0:
        return "Fair", "Insufficient P/E data"
    if pe > sector_median * PE_CAUTION_MULT:
        return "Caution", (
            f"P/E {pe:.1f} > {PE_CAUTION_MULT}x sector median {sector_median:.1f}"
        )
    if pe < sector_median * PE_DISCOUNT_MULT:
        return "Discount", (
            f"P/E {pe:.1f} < {PE_DISCOUNT_MULT}x sector median {sector_median:.1f}"
        )
    return "Fair", f"P/E {pe:.1f} within band of sector median {sector_median:.1f}"


def build_valuation_summary() -> pd.DataFrame:
    """One row per company: latest multiples, FCF yield, sector-relative flag."""
    mc = _read("SELECT * FROM market_cap")
    companies = _read(
        """
        SELECT c.id, c.company_name, s.broad_sector AS sector
        FROM companies c
        JOIN sectors s ON s.company_id = c.id
        """
    )
    fcf = (
        _read("SELECT company_id, year, free_cash_flow_cr FROM financial_ratios")
        .sort_values("year")
        .groupby("company_id")
        .tail(1)
        .set_index("company_id")["free_cash_flow_cr"]
        .rename("fcf_cr")
    )

    latest = mc[mc["year"] == mc["year"].max()].copy()
    median_5y = (
        mc.sort_values("year")
        .groupby("company_id")
        .tail(5)
        .groupby("company_id")["pe_ratio"]
        .median()
        .rename("5yr_median_PE")
    )
    latest = latest.merge(median_5y, on="company_id", how="left")
    latest = latest.merge(fcf, on="company_id", how="left")
    latest["FCF_yield_pct"] = (
        latest["fcf_cr"] / latest["market_cap_crore"] * 100
    ).round(2)

    summary = latest.merge(
        companies, left_on="company_id", right_on="id", how="left"
    )
    sector_median = (
        summary.groupby("sector")["pe_ratio"].median().rename("sector_median_pe")
    )
    summary = summary.merge(sector_median, on="sector", how="left")
    summary["PE_vs_sector_median_pct"] = (
        (summary["pe_ratio"] - summary["sector_median_pe"])
        / summary["sector_median_pe"]
        * 100
    ).round(1)

    flags = summary.apply(
        lambda r: flag_company(r["pe_ratio"], r["sector_median_pe"]),
        axis=1,
        result_type="expand",
    )
    flags.columns = ["flag", "rationale"]
    summary = summary.join(flags)

    summary = summary.rename(
        columns={"pe_ratio": "P/E", "pb_ratio": "P/B", "ev_ebitda": "EV/EBITDA"}
    )
    return summary.sort_values("company_id").reset_index(drop=True)


def write_outputs(summary: pd.DataFrame) -> None:
    """Write valuation_summary.xlsx and valuation_flags.csv to OUTPUT_DIR."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary[SUMMARY_COLUMNS].to_excel(
        f"{OUTPUT_DIR}/valuation_summary.xlsx", index=False
    )
    flagged = summary[summary["flag"] != "Fair"]
    flagged[FLAG_COLUMNS].to_csv(f"{OUTPUT_DIR}/valuation_flags.csv", index=False)
    logger.info(
        "Wrote %d companies to valuation_summary.xlsx; %d Caution/Discount flags",
        len(summary),
        len(flagged),
    )


def main() -> None:
    """Build and export the Module 6 valuation outputs."""
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    write_outputs(build_valuation_summary())


if __name__ == "__main__":
    main()