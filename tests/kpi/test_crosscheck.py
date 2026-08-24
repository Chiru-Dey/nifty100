"""Unit tests for Day 13 cross-check and edge case logging."""

import logging
from pathlib import Path

import pandas as pd

from src.analytics.crosscheck import (
    categorise,
    configure_edge_logging,
    cross_check,
    log_debt_free_substitutions,
    verify_financials_suppression,
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


def _snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company_id": "TCS",
                "year": "2024-03",
                "return_on_capital_pct": 50.0,
                "return_on_equity_pct": 45.0,
                "roce_percentage": 80.0,
                "roe_percentage": 44.0,
            }
        ]
    )

def test_categorise_data_source_issue():
    assert categorise(45.0, 0.52, 0.25) == "data_source_issue"


def test_categorise_version_difference():
    assert categorise(20.0, 24.0, 0.25) == "version_difference"


def test_categorise_formula_mismatch():
    assert categorise(10.0, 60.0, 0.25) == "formula_mismatch"


def test_cross_check_flags_roce_anomaly():
    out = cross_check(_snapshot(), 5.0, 0.25)
    assert len(out) == 1
    assert out.iloc[0]["metric"] == "ROCE"
    assert out.iloc[0]["category"] == "formula_mismatch"


def test_cross_check_within_tolerance_empty():
    snapshot = _snapshot()
    snapshot["roce_percentage"] = 52.0
    assert cross_check(snapshot, 5.0, 0.25).empty


def test_verify_financials_suppression():
    df = pd.DataFrame(
        [
            {
                "company_id": "HDFCBANK",
                "year": "2024-03",
                "sales": 100.0,
                "operating_profit": 50.0,
                "other_income": 1.0,
                "interest": 10.0,
                "equity_capital": 100.0,
                "reserves": 0.0,
                "borrowings": 800.0,
                "investments": 10.0,
                "total_assets": 1000.0,
                "broad_sector": "Financials",
            },
            {
                "company_id": "TATASTEEL",
                "year": "2024-03",
                "sales": 100.0,
                "operating_profit": 20.0,
                "other_income": 1.0,
                "interest": 5.0,
                "equity_capital": 100.0,
                "reserves": 0.0,
                "borrowings": 800.0,
                "investments": 10.0,
                "total_assets": 1000.0,
                "broad_sector": "Materials",
            },
        ]
    )
    assert verify_financials_suppression(df, CONFIG) == 0
    
def test_log_debt_free_substitutions(caplog):
    df = pd.DataFrame([{"company_id": "TCS", "year": "2024-03", "interest": 0.0}])
    with caplog.at_level(logging.INFO):
        assert log_debt_free_substitutions(df) == 1
    assert "Debt-free substitution" in caplog.text


def test_configure_edge_logging(tmp_path):
    path = tmp_path / "ratio_edge_cases.log"
    configure_edge_logging(path)
    root = logging.getLogger()
    hit = [
        h
        for h in root.handlers
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename) == path
    ]
    assert hit
    root.handlers.remove(hit[0])