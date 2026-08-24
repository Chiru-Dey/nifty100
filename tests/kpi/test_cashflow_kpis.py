"""Unit tests for Day 11 cash flow KPIs and capital allocation."""

import pandas as pd

from src.analytics.cashflow_kpis import (
    capital_allocation_frame,
    capital_allocation_label,
    capex_intensity,
    capex_intensity_label,
    cfo_quality_label,
    cfo_quality_score,
    fcf_conversion,
    free_cash_flow,
)

CONFIG = {"shareholder_returns_cfo_pat": 1.5}


def test_free_cash_flow_negative_allowed():
    assert free_cash_flow(100, -60) == 40.0
    assert free_cash_flow(50, -80) == -30.0


def test_free_cash_flow_missing_cfi():
    assert free_cash_flow(100, None) is None


def test_cfo_quality_score_average():
    pairs = [(110, 100), (120, 100), (None, 50), (90, 100), (130, 100)]
    assert cfo_quality_score(pairs) == (1.1 + 1.2 + 0.9 + 1.3) / 4


def test_cfo_quality_score_zero_pat():
    assert cfo_quality_score([(110, 100), (120, 0)]) is None


def test_cfo_quality_label_tiers():
    assert cfo_quality_label(1.2, 1.0, 0.5) == "High Quality"
    assert cfo_quality_label(0.7, 1.0, 0.5) == "Moderate"
    assert cfo_quality_label(0.3, 1.0, 0.5) == "Accrual Risk"


def test_capex_intensity_and_label():
    assert capex_intensity(-80, 2000) == 4.0
    assert capex_intensity_label(2.0, 3.0, 8.0) == "Asset Light"
    assert capex_intensity_label(5.0, 3.0, 8.0) == "Moderate"
    assert capex_intensity_label(10.0, 3.0, 8.0) == "Capital Intensive"


def test_fcf_conversion():
    assert fcf_conversion(60, 100) == 60.0
    assert fcf_conversion(60, 0) is None
    assert fcf_conversion(60, -100) is None


def test_capital_allocation_reinvestor_vs_shareholder_returns():
    assert capital_allocation_label(100, -50, -20, 0.8, 1.5) == "Reinvestor"
    assert capital_allocation_label(100, -50, -20, 2.0, 1.5) == "Shareholder Returns"


def test_capital_allocation_pattern_labels():
    assert capital_allocation_label(-100, 50, 20, None, 1.5) == "Distress Signal"
    assert capital_allocation_label(-100, -50, 20, None, 1.5) == "Growth Funded by Debt"
    assert capital_allocation_label(100, 50, -20, None, 1.5) == "Liquidating Assets"
    assert capital_allocation_label(100, 50, 20, None, 1.5) == "Cash Accumulator"
    assert capital_allocation_label(-100, -50, -20, None, 1.5) == "Pre-Revenue"
    assert capital_allocation_label(100, -50, 20, None, 1.5) == "Mixed"


def test_capital_allocation_frame_columns():
    df = pd.DataFrame(
        [
            {
                "company_id": "TCS",
                "year": "2023-03",
                "operating_activity": 100.0,
                "investing_activity": -50.0,
                "financing_activity": -20.0,
                "net_profit": 50.0,
            }
        ]
    )
    alloc = capital_allocation_frame(df, CONFIG)
    assert list(alloc.columns) == [
        "company_id",
        "year",
        "cfo_sign",
        "cfi_sign",
        "cff_sign",
        "pattern_label",
    ]
    assert alloc.iloc[0]["pattern_label"] == "Shareholder Returns"