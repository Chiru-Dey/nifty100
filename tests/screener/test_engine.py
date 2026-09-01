import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.screener.engine import apply_filters, screen

BASE = {"company_id": ["A", "B", "C", "D"], "year": ["2024-03"] * 4,
        "sector": ["Information Technology", "Information Technology", "Financials", "Information Technology"],
        "return_on_equity_pct": [20.0, 10.0, 30.0, 18.0],
        "debt_to_equity": [0.5, 0.5, 0.5, 0.8],
        "free_cash_flow_cr": [10.0, 10.0, 10.0, -5.0],
        "interest_coverage": ["Debt Free", 8.0, 2.0, 6.0]}


def frame() -> pd.DataFrame:
    return pd.DataFrame(BASE)


def test_quality_filters():
    result = apply_filters(frame(), {"roe_min": 15, "de_max": 1.0, "fcf_min": 0})
    assert result["company_id"].tolist() == ["A"]


def test_financials_carve_out():
    with_de = apply_filters(frame(), {"de_max": 1.0})
    assert "C" not in with_de["company_id"].tolist()
    without_de = apply_filters(frame(), {"roe_min": 15})
    assert "C" in without_de["company_id"].tolist()


def test_icr_debt_free_passes():
    result = apply_filters(frame(), {"icr_min": 5})
    assert sorted(result["company_id"]) == ["A", "B", "D"]


def test_composite_score_bounds_and_ranking():
    result = screen(frame(), {"filters": {"roe_min": 0}})
    assert result["composite_quality_score"].between(0, 100).all()
    assert result["composite_quality_score"].is_monotonic_decreasing