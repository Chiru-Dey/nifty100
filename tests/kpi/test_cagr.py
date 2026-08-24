"""Unit tests for Day 10 CAGR engine."""

import pandas as pd
import pytest

from src.analytics.cagr import CAGR_COLUMNS, cagr, compute_cagr


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company_id": "TCS",
                "year": "2020-03",
                "sales": 100.0,
                "net_profit": 10.0,
                "eps": 5.0,
            },
            {
                "company_id": "TCS",
                "year": "2023-03",
                "sales": 133.1,
                "net_profit": -10.0,
                "eps": -2.0,
            },
        ]
    )


def test_cagr_normal():
    value, flag = cagr(100, 161, 5)
    assert value == pytest.approx(10.0, abs=0.1)
    assert flag is None


def test_cagr_turnaround():
    assert cagr(-100, 200, 5) == (None, "TURNAROUND")


def test_cagr_decline_to_loss():
    assert cagr(100, -50, 3) == (None, "DECLINE_TO_LOSS")


def test_cagr_both_negative():
    assert cagr(-100, -50, 3) == (None, "BOTH_NEGATIVE")


def test_cagr_zero_base():
    assert cagr(0, 100, 3) == (None, "ZERO_BASE")


def test_cagr_insufficient():
    assert cagr(None, 100, 3) == (None, "INSUFFICIENT")


def test_compute_cagr_revenue_3yr():
    out = compute_cagr(_frame())
    latest = out[out["year"] == "2023-03"].iloc[0]
    assert latest["revenue_cagr_3yr"] == pytest.approx(10.0, abs=0.01)
    assert pd.isna(latest["revenue_cagr_3yr_flag"])


def test_compute_cagr_insufficient_flag():
    out = compute_cagr(_frame())
    earliest = out[out["year"] == "2020-03"].iloc[0]
    assert pd.isna(earliest["revenue_cagr_3yr"])
    assert earliest["revenue_cagr_3yr_flag"] == "INSUFFICIENT"


def test_compute_cagr_pat_decline_to_loss():
    out = compute_cagr(_frame())
    latest = out[out["year"] == "2023-03"].iloc[0]
    assert pd.isna(latest["pat_cagr_3yr"])
    assert latest["pat_cagr_3yr_flag"] == "DECLINE_TO_LOSS"

def test_cagr_columns_present():
    out = compute_cagr(_frame())
    assert set(CAGR_COLUMNS) <= set(out.columns)
    assert len(CAGR_COLUMNS) == 18