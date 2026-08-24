import pandas as pd

from src.etl.validator import validate_all

YEARS = [f"{y}-03" for y in range(2020, 2025)]


def _companies() -> pd.DataFrame:
    return pd.DataFrame(
        {"id": ["TCS", "INFY"], "company_name": ["Tata Consultancy", "Infosys"]}
    )


def _pl() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": cid,
            "year": y,
            "sales": 100.0,
            "operating_profit": 20.0,
            "opm_percentage": 20.0,
            "net_profit": 10.0,
            "eps": 5.0,
            "tax_percentage": 25.0,
            "dividend_payout": 40.0,
        }
        for cid in ("TCS", "INFY")
        for y in YEARS
    )


def _bs() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": cid,
            "year": y,
            "total_assets": 100.0,
            "total_liabilities": 100.0,
            "fixed_assets": 10.0,
        }
        for cid in ("TCS", "INFY")
        for y in YEARS
    )


def _cf() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "company_id": cid,
            "year": y,
            "operating_activity": 10.0,
            "investing_activity": -5.0,
            "financing_activity": -2.0,
            "net_cash_flow": 3.0,
        }
        for cid in ("TCS", "INFY")
        for y in YEARS
    )


def _rules(**overrides) -> set:
    frames = {
        "companies": _companies(),
        "profitandloss": _pl(),
        "balancesheet": _bs(),
        "cashflow": _cf(),
    }
    frames.update(overrides)
    return set(validate_all(frames)["rule"])


def test_clean_frames_pass() -> None:
    assert not _rules()


def test_dq01_duplicate_company() -> None:
    companies = pd.concat([_companies(), _companies().iloc[[0]]], ignore_index=True)
    assert "DQ-01" in _rules(companies=companies)


def test_dq02_duplicate_pk() -> None:
    pl = pd.concat([_pl(), _pl().iloc[[0]]], ignore_index=True)
    assert "DQ-02" in _rules(profitandloss=pl)


def test_dq03_orphan() -> None:
    pl = _pl()
    pl.loc[0, "company_id"] = "ZZZZ"
    assert "DQ-03" in _rules(profitandloss=pl)


def test_dq04_bs_imbalance() -> None:
    bs = _bs()
    bs.loc[0, "total_liabilities"] = 1020.0
    assert "DQ-04" in _rules(balancesheet=bs)


def test_dq06_zero_sales() -> None:
    pl = _pl()
    pl.loc[0, "sales"] = 0.0
    assert "DQ-06" in _rules(profitandloss=pl)


def test_dq09_cf_mismatch() -> None:
    cf = _cf()
    cf.loc[0, "net_cash_flow"] = 50.0
    assert "DQ-09" in _rules(cashflow=cf)


def test_dq10_negative_fixed_assets() -> None:
    bs = _bs()
    bs.loc[0, "fixed_assets"] = -1.0
    assert "DQ-10" in _rules(balancesheet=bs)


def test_dq11_tax_range() -> None:
    pl = _pl()
    pl.loc[0, "tax_percentage"] = 75.0
    assert "DQ-11" in _rules(profitandloss=pl)


def test_dq12_payout_cap() -> None:
    pl = _pl()
    pl.loc[0, "dividend_payout"] = 250.0
    assert "DQ-12" in _rules(profitandloss=pl)


def test_dq14_eps_sign() -> None:
    pl = _pl()
    pl.loc[0, "eps"] = -1.0
    assert "DQ-14" in _rules(profitandloss=pl)


def test_dq16_coverage() -> None:
    pl = _pl()
    pl = pl[~((pl["company_id"] == "TCS") & (pl["year"] >= "2022-03"))]
    assert "DQ-16" in _rules(profitandloss=pl)
