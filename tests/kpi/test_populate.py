"""Unit tests for Day 12 financial_ratios population."""

import pandas as pd
import pytest

from src.analytics.populate import (
    ALL_COLUMNS,
    _winsorise_scale,
    book_value_per_share,
    build_full_frame,
    composite_quality_score,
    compute_base_columns,
)

CONFIG = {
    "roce_benchmarks": {"default": {"good": 15.0, "excellent": 25.0}},
    "high_leverage_de": 5.0,
    "icr_warning_threshold": 1.5,
    "cfo_quality_window_years": 5,
    "cfo_quality_high": 1.0,
    "cfo_quality_moderate": 0.5,
    "capex_asset_light_pct": 3.0,
    "capex_capital_intensive_pct": 8.0,
    "shareholder_returns_cfo_pat": 1.5,
}

REQUIRED = [
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "return_on_equity_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "free_cash_flow_cr",
    "capex_cr",
    "earnings_per_share",
    "book_value_per_share",
    "dividend_payout_ratio_pct",
    "total_debt_cr",
    "cash_from_operations_cr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
    "composite_quality_score",
]


def _frame() -> pd.DataFrame:
    row = {
        "company_id": "TCS",
        "sales": 100.0,
        "operating_profit": 25.0,
        "opm_percentage": 25.0,
        "depreciation": 5.0,
        "other_income": 2.0,
        "interest": 0.0,
        "net_profit": 20.0,
        "eps": 10.0,
        "dividend_payout": 40.0,
        "equity_capital": 10.0,
        "reserves": 90.0,
        "borrowings": 0.0,
        "investments": 20.0,
        "total_assets": 150.0,
        "operating_activity": 30.0,
        "investing_activity": -10.0,
        "financing_activity": -15.0,
        "broad_sector": "Information Technology",
        "face_value": 1.0,
    }
    return pd.DataFrame(
        [dict(row, year="2018-03"), dict(row, year="2023-03", sales=161.0)]
    )


def test_book_value_per_share_normal():
    assert book_value_per_share(100, 100, 10) == pytest.approx(20.0)


def test_book_value_per_share_zero_face_value():
    assert book_value_per_share(100, 100, 0) is None


def test_compute_base_columns_passthrough():
    out = compute_base_columns(_frame()).iloc[0]
    assert out["capex_cr"] == 10.0
    assert out["earnings_per_share"] == 10.0
    assert out["total_debt_cr"] == 0.0
    assert out["cash_from_operations_cr"] == 30.0


def test_winsorise_scale_bounds():
    scaled = _winsorise_scale(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]))
    assert scaled.min() == pytest.approx(0.0)
    assert scaled.max() == pytest.approx(100.0)
    inverted = _winsorise_scale(
        pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]),
        higher_better=False,
    )
    assert inverted.iloc[0] == pytest.approx(100.0)


def test_composite_quality_score_bounds():
    full = build_full_frame(_frame(), CONFIG)
    scores = full["composite_quality_score"].dropna()
    assert ((scores >= 0) & (scores <= 100)).all()


def test_composite_quality_score_missing_component():
    frame = pd.DataFrame(
        {
            "sales": [100.0, 100.0],
            "free_cash_flow_cr": [10.0, 20.0],
            "return_on_equity_pct": [15.0, float("nan")],
            "return_on_capital_pct": [20.0, 25.0],
            "debt_to_equity": [0.5, 1.0],
        }
    )
    assert composite_quality_score(frame).notna().tolist() == [True, False]


def test_build_full_frame_required_columns():
    full = build_full_frame(_frame(), CONFIG)
    assert set(REQUIRED) <= set(full.columns)


def test_all_columns_schema_types():
    assert set(REQUIRED) <= set(ALL_COLUMNS)
    assert set(ALL_COLUMNS.values()) <= {"REAL", "TEXT", "INTEGER"}