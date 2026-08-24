import pandas as pd

from src.etl.loader import clean_frames, normalise_frame


def test_normalise_frame_keeps_valid_rows() -> None:
    df = pd.DataFrame({"company_id": ["tcs", " infy "], "year": ["Mar-23", "Mar-23"]})
    clean, rejected = normalise_frame("profitandloss", df)
    assert len(clean) == 2
    assert rejected.empty


def test_normalise_frame_rejects_bad_ticker() -> None:
    df = pd.DataFrame({"company_id": ["", "TCS"], "year": ["Mar-23", "Mar-23"]})
    clean, rejected = normalise_frame("profitandloss", df)
    assert len(clean) == 1
    assert rejected["file"].iloc[0] == "profitandloss"


def test_normalise_frame_rejects_bad_year() -> None:
    df = pd.DataFrame({"company_id": ["TCS"], "year": ["garbage"]})
    clean, rejected = normalise_frame("profitandloss", df)
    assert clean.empty
    assert len(rejected) == 1


def test_clean_frames_dedups_market_cap() -> None:
    frames = {
        "companies": pd.DataFrame({"id": ["TCS"]}),
        "market_cap": pd.DataFrame(
            {
                "company_id": ["TCS", "TCS"],
                "year": [2024, 2024],
                "pe_ratio": [20.0, 25.0],
            }
        ),
    }
    cleaned = clean_frames(frames)
    assert len(cleaned["market_cap"]) == 1
    assert cleaned["market_cap"]["pe_ratio"].iloc[0] == 25.0
