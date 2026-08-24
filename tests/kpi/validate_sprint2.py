

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.analytics.ratios import DB_PATH

SPOT_TICKERS = ("TCS", "HDFCBANK", "RELIANCE", "INFY", "ITC")
MIN_ROW_COUNT = 1100

REQUIRED_COLUMNS = [    
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "return_on_equity_pct",
    "return_on_capital_pct",
    "return_on_assets_pct",
    "roce_rating",    
    "debt_to_equity",
    "high_leverage_flag",
    "interest_coverage",
    "icr_label",
    "icr_warning_flag",
    "net_debt_cr",
    "asset_turnover",
    # Day 10 — CAGR
    "revenue_cagr_3yr",
    "revenue_cagr_5yr",
    "revenue_cagr_10yr",
    "pat_cagr_3yr",
    "pat_cagr_5yr",
    "pat_cagr_10yr",
    "eps_cagr_3yr",
    "eps_cagr_5yr",
    "eps_cagr_10yr",
    # Day 11 — Cash Flow
    "free_cash_flow_cr",
    "cfo_quality_score",
    "cfo_quality_label",
    "capex_intensity_pct",
    "capex_intensity_label",
    "fcf_conversion_pct",
    "capital_allocation_label",
    # Day 12 — Base / Passthrough
    "capex_cr",
    "earnings_per_share",
    "book_value_per_share",
    "dividend_payout_ratio_pct",
    "total_debt_cr",
    "cash_from_operations_cr",
    "composite_quality_score",
]

VALID_CAGR_FLAGS = {
    None,
    "INSUFFICIENT",
    "ZERO_BASE",
    "DECLINE_TO_LOSS",
    "TURNAROUND",
    "BOTH_NEGATIVE",
}

VALID_ROCE_RATINGS = {None, "excellent", "good", "below_benchmark"}
VALID_CFO_LABELS = {None, "High Quality", "Moderate", "Accrual Risk"}
VALID_CAPEX_LABELS = {None, "Asset Light", "Moderate", "Capital Intensive"}
VALID_ALLOCATION_LABELS = {
    None,
    "Reinvestor",
    "Shareholder Returns",
    "Cash Accumulator",
    "Liquidating Assets",
    "Distress Signal",
    "Growth Funded by Debt",
    "Pre-Revenue",
    "Divestment",
    "Mixed",
}


@pytest.fixture(scope="module")
def ratios_df() -> pd.DataFrame:
    """Load financial_ratios once for the entire sweep."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql("SELECT * FROM financial_ratios", conn)


@pytest.fixture(scope="module")
def merged_df() -> pd.DataFrame:
    """Load P&L + sectors for cross-referencing."""
    with sqlite3.connect(DB_PATH) as conn:
        pl = pd.read_sql("SELECT company_id, year, interest FROM profitandloss", conn)
        sectors = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)
    return pl.merge(sectors, on="company_id", how="left")


# ── AC-04: Row count gate ─────────────────────────────────────
class TestRowCountGate:
    def test_min_row_count(self, ratios_df):
        assert len(ratios_df) >= MIN_ROW_COUNT, (
            f"AC-04 failed: {len(ratios_df)} rows < {MIN_ROW_COUNT}"
        )


# ── Schema completeness ───────────────────────────────────────
class TestSchemaCompleteness:
    def test_all_required_columns_present(self, ratios_df):
        missing = set(REQUIRED_COLUMNS) - set(ratios_df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_no_all_null_ratio_columns(self, ratios_df):
        for col in REQUIRED_COLUMNS:
            assert ratios_df[col].notna().any(), f"Column {col} is entirely NULL"


# ── Spot-check: 5 companies have data ─────────────────────────
class TestSpotCheck:
    @pytest.mark.parametrize("ticker", SPOT_TICKERS)
    def test_ticker_present(self, ratios_df, ticker):
        subset = ratios_df[ratios_df["company_id"] == ticker]
        assert len(subset) >= 5, f"{ticker} has only {len(subset)} rows"

    @pytest.mark.parametrize("ticker", SPOT_TICKERS)
    def test_ticker_has_roe(self, ratios_df, ticker):
        subset = ratios_df[ratios_df["company_id"] == ticker]
        assert subset["return_on_equity_pct"].notna().any(), f"{ticker} ROE all NULL"

    @pytest.mark.parametrize("ticker", SPOT_TICKERS)
    def test_ticker_has_revenue_cagr_5yr(self, ratios_df, ticker):
        subset = ratios_df[ratios_df["company_id"] == ticker]
        assert subset["revenue_cagr_5yr"].notna().any(), f"{ticker} 5yr CAGR all NULL"


# ── Value range checks ────────────────────────────────────────
class TestValueRanges:
    def test_composite_score_bounds(self, ratios_df):
        valid = ratios_df["composite_quality_score"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_roce_rating_values(self, ratios_df):
        values = set(ratios_df["roce_rating"].dropna().unique()) | {None}
        assert values <= VALID_ROCE_RATINGS

    def test_cfo_quality_label_values(self, ratios_df):
        values = set(ratios_df["cfo_quality_label"].dropna().unique()) | {None}
        assert values <= VALID_CFO_LABELS

    def test_capex_intensity_label_values(self, ratios_df):
        values = set(ratios_df["capex_intensity_label"].dropna().unique()) | {None}
        assert values <= VALID_CAPEX_LABELS

    def test_capital_allocation_label_values(self, ratios_df):
        values = set(ratios_df["capital_allocation_label"].dropna().unique()) | {None}
        assert values <= VALID_ALLOCATION_LABELS


# ── CAGR flag validation ──────────────────────────────────────
class TestCAGRFlags:
    @pytest.mark.parametrize(
        "col",
        [
            "revenue_cagr_3yr_flag",
            "revenue_cagr_5yr_flag",
            "revenue_cagr_10yr_flag",
            "pat_cagr_3yr_flag",
            "pat_cagr_5yr_flag",
            "pat_cagr_10yr_flag",
            "eps_cagr_3yr_flag",
            "eps_cagr_5yr_flag",
            "eps_cagr_10yr_flag",
        ],
    )
    def test_cagr_flag_values(self, ratios_df, col):
        values = set(ratios_df[col].dropna().unique()) | {None}
        assert values <= VALID_CAGR_FLAGS, f"Invalid flag in {col}: {values - VALID_CAGR_FLAGS}"


# ── Financials D/E suppression (R-04) ─────────────────────────
class TestFinancialsSuppression:
    def test_no_high_leverage_flag_for_financials(self, ratios_df, merged_df):
        financials = merged_df[merged_df["broad_sector"] == "Financials"][
            "company_id"
        ].unique()
        fin_rows = ratios_df[ratios_df["company_id"].isin(financials)]
        flagged = fin_rows[fin_rows["high_leverage_flag"] == 1]
        assert flagged.empty, (
            f"Financials D/E suppression violated: {flagged['company_id'].unique()}"
        )


# ── Debt-free ICR label ───────────────────────────────────────
class TestDebtFreeLabel:
    def test_debt_free_label_where_interest_zero(self, ratios_df, merged_df):
        zero_interest = merged_df[merged_df["interest"] == 0][
            ["company_id", "year"]
        ]
        if zero_interest.empty:
            pytest.skip("No zero-interest rows in dataset")
        joined = zero_interest.merge(
            ratios_df[["company_id", "year", "icr_label"]],
            on=["company_id", "year"],
        )
        debt_free = joined[joined["icr_label"] == "Debt Free"]
        assert len(debt_free) == len(joined), (
            f"Missing Debt Free label for {len(joined) - len(debt_free)} rows"
        )


# ── Cross-module consistency ──────────────────────────────────
class TestCrossModuleConsistency:
    def test_fcf_equals_cfo_plus_cfi(self, ratios_df):
        """FCF should equal cash_from_operations + capex (sign-adjusted)."""
        with sqlite3.connect(DB_PATH) as conn:
            cf = pd.read_sql(
                "SELECT company_id, year, operating_activity, investing_activity "
                "FROM cashflow",
                conn,
            )
        joined = ratios_df.merge(cf, on=["company_id", "year"])
        valid = joined.dropna(
            subset=["free_cash_flow_cr", "operating_activity", "investing_activity"]
        )
        if valid.empty:
            pytest.skip("No rows with all three values present")
        expected = valid["operating_activity"] + valid["investing_activity"]
        diff = (valid["free_cash_flow_cr"] - expected).abs()
        assert (diff < 0.01).all(), f"FCF mismatch in {(diff >= 0.01).sum()} rows"