"""Unit tests for Day 9 leverage and efficiency ratios."""

import pytest

from src.analytics.leverage import (
    asset_turnover,
    debt_to_equity,
    high_leverage_flag,
    icr_label,
    icr_warning_flag,
    interest_coverage,
    net_debt,
)


def test_debt_to_equity_normal():
    assert debt_to_equity(500, 100, 400) == pytest.approx(1.0)


def test_debt_to_equity_debt_free_returns_zero():
    assert debt_to_equity(0, 100, 400) == 0.0


def test_high_leverage_flag_financials_carve_out():
    assert high_leverage_flag(6.0, "Materials", 5.0) is True
    assert high_leverage_flag(6.0, "Financials", 5.0) is False


def test_interest_coverage_normal():
    assert interest_coverage(480, 20, 100) == pytest.approx(5.0)


def test_interest_coverage_zero_interest_returns_none():
    assert interest_coverage(480, 20, 0) is None


def test_icr_label_debt_free():
    assert icr_label(None, 0) == "Debt Free"
    assert icr_label(5.0, 100) is None


def test_icr_warning_flag():
    assert icr_warning_flag(1.2, 1.5) is True
    assert icr_warning_flag(3.0, 1.5) is False
    assert icr_warning_flag(None, 1.5) is False


def test_net_debt_and_asset_turnover():
    assert net_debt(100, 40) == pytest.approx(60.0)
    assert net_debt(0, 50) == pytest.approx(-50.0)
    assert asset_turnover(200, 100) == pytest.approx(2.0)
    assert asset_turnover(200, 0) is None