import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analytics.peer import compute_peer_percentiles

GROUPS = pd.DataFrame({
    "peer_group_name": ["IT Services"] * 3,
    "company_id": ["TCS", "INFY", "HCLTECH"],
})
RATIOS = pd.DataFrame({
    "company_id": ["TCS", "INFY", "HCLTECH"],
    "year": ["2024-03"] * 3,
    "return_on_equity_pct": [50.0, 40.0, 30.0],
    "debt_to_equity": [0.1, 0.2, 0.3],
})


def test_highest_roe_gets_highest_rank():
    pp = compute_peer_percentiles(GROUPS, RATIOS)
    roe = pp[pp["metric"] == "ROE"]
    assert roe.loc[roe["value"].idxmax(), "company_id"] == "TCS"
    assert roe.loc[roe["percentile_rank"].idxmax(), "company_id"] == "TCS"
    assert roe.loc[roe["percentile_rank"].idxmax(), "percentile_rank"] == 1.0


def test_de_inverted():
    pp = compute_peer_percentiles(GROUPS, RATIOS)
    de = pp[pp["metric"] == "D/E"]
    assert de.loc[de["value"].idxmin(), "percentile_rank"] == 1.0


def test_unassigned_company_excluded():
    pp = compute_peer_percentiles(GROUPS, RATIOS)
    assert "WIPRO" not in pp["company_id"].tolist()