import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.etl.dq_rules import (
    SEVERITIES,
    dq01_company_pk_unique, dq02_annual_pk_unique, dq03_fk_integrity,
    dq04_bs_balance, dq05_opm_cross_check, dq06_positive_sales,
    dq07_year_format, dq08_ticker_format, dq09_net_cash_check,
    dq10_non_negative_fixed_assets, dq11_tax_rate_range, dq12_dividend_payout_cap,
    dq13_url_validity, dq14_eps_sign_consistency,
)


def test_dq01_duplicate_pk():
    assert dq01_company_pk_unique(pd.DataFrame({"id": ["TCS", "TCS"]}))
    assert not dq01_company_pk_unique(pd.DataFrame({"id": ["TCS", "INFY"]}))
    assert SEVERITIES["DQ-01"] == "CRITICAL"


def test_dq02_duplicate_annual_pk():
    df = pd.DataFrame({"company_id": ["TCS", "TCS"], "year": ["2023-03", "2023-03"]})
    assert dq02_annual_pk_unique(df).sum() == 1
    assert SEVERITIES["DQ-02"] == "CRITICAL"


def test_dq03_orphan_fk():
    child = pd.DataFrame({"company_id": ["TCS", "XYZ"]})
    parents = pd.DataFrame({"id": ["TCS"]})
    assert dq03_fk_integrity(child, parents).tolist() == [False, True]
    assert SEVERITIES["DQ-03"] == "CRITICAL"


def test_dq04_bs_balance():
    df = pd.DataFrame({"total_assets": [1000, 1000], "total_liabilities": [1020, 999]})
    assert dq04_bs_balance(df).tolist() == [True, False]
    assert SEVERITIES["DQ-04"] == "WARNING"


def test_dq05_opm_cross_check():
    df = pd.DataFrame({"sales": [100], "operating_profit": [20], "opm_percentage": [25.0]})
    assert dq05_opm_cross_check(df).iloc[0]
    assert SEVERITIES["DQ-05"] == "WARNING"


def test_dq06_zero_sales():
    assert dq06_positive_sales(pd.DataFrame({"sales": [0]})).iloc[0]
    assert SEVERITIES["DQ-06"] == "WARNING"


def test_dq07_year_format():
    df = pd.DataFrame({"year": ["2023-03", "garbage"]})
    assert dq07_year_format(df).tolist() == [False, True]
    assert SEVERITIES["DQ-07"] == "CRITICAL"


def test_dq08_ticker_format():
    df = pd.DataFrame({"company_id": ["TCS", "X"]})
    assert dq08_ticker_format(df).tolist() == [False, True]
    assert SEVERITIES["DQ-08"] == "CRITICAL"


def test_dq09_net_cash_mismatch():
    df = pd.DataFrame({"operating_activity": [100], "investing_activity": [-40], "financing_activity": [-10], "net_cash_flow": [50]})
    assert not dq09_net_cash_check(df).iloc[0]
    df.loc[0, "net_cash_flow"] = 80
    assert dq09_net_cash_check(df).iloc[0]
    assert SEVERITIES["DQ-09"] == "WARNING"

def test_dq10_negative_fixed_assets():
    assert dq10_non_negative_fixed_assets(pd.DataFrame({"fixed_assets": [-5]})).iloc[0]
    assert SEVERITIES["DQ-10"] == "WARNING"


def test_dq11_tax_rate_range():
    df = pd.DataFrame({"tax_percentage": [25, 75]})
    assert dq11_tax_rate_range(df).tolist() == [False, True]
    assert SEVERITIES["DQ-11"] == "WARNING"


def test_dq12_payout_cap():
    assert dq12_dividend_payout_cap(pd.DataFrame({"dividend_payout": [250]})).iloc[0]
    assert SEVERITIES["DQ-12"] == "WARNING"


def test_dq13_url_status():
    assert dq13_url_validity(pd.Series([200, 404])).tolist() == [False, True]
    assert SEVERITIES["DQ-13"] == "WARNING"


def test_dq14_eps_sign():
    df = pd.DataFrame({"net_profit": [100], "eps": [-2]})
    assert dq14_eps_sign_consistency(df).iloc[0]
    assert SEVERITIES["DQ-14"] == "WARNING"