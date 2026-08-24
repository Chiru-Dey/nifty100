"""Unit tests for Day 8 profitability ratios."""

import logging

import pandas as pd
import pytest

from src.analytics.ratios import (
    check_opm_mismatches,
    net_profit_margin,
    operating_profit_margin,
    rate_roce,
    return_on_assets,
    return_on_capital,
    return_on_equity,
)

BENCHMARKS = {
    "default": {"good": 15.0, "excellent": 25.0},
    "Financials": {"good": 12.0, "excellent": 18.0},
}


def test_net_profit_margin_normal():
    assert net_profit_margin(20, 200) == pytest.approx(10.0)


def test_net_profit_margin_zero_sales():
    assert net_profit_margin(20, 0) is None


def test_operating_profit_margin_normal():
    assert operating_profit_margin(50, 200) == pytest.approx(25.0)


def test_opm_cross_check_mismatch(caplog):
    df = pd.DataFrame(
        [
            {
                "company_id": "TCS",
                "year": "2023-03",
                "operating_profit": 50,
                "sales": 200,
                "opm_percentage": 21.5,
            }
        ]
    )
    with caplog.at_level(logging.WARNING):
        assert check_opm_mismatches(df, 1.0) == 1
    assert "DQ-05" in caplog.text


def test_return_on_equity_normal():
    assert return_on_equity(100, 400, 100) == pytest.approx(20.0)


def test_return_on_equity_negative_equity():
    assert return_on_equity(100, -50, 0) is None


def test_roce_sector_relative_benchmark():
    roce = return_on_capital(80, 200, 100, 100)
    assert roce == pytest.approx(20.0)
    assert rate_roce(roce, "Financials", BENCHMARKS) == "excellent"
    assert rate_roce(roce, "Materials", BENCHMARKS) == "good"


def test_return_on_assets_zero_assets():
    assert return_on_assets(100, 0) is None