import pytest

from src.etl.normaliser import normalize_ticker, normalize_year

YEAR_CASES = [
    ("Mar-23", "2023-03"),
    ("Mar 23", "2023-03"),
    ("March-2023", "2023-03"),
    ("December-2022", "2022-12"),
    ("2023", "2023-03"),
    (2023, "2023-03"),
    (2023.0, "2023-03"),
    ("FY23", "2023-03"),
    ("fy24", "2024-03"),
    ("FY2024", "2024-03"),
    ("Dec-22", "2022-12"),
    ("Jun-23", "2023-06"),
    ("Apr-21", "2021-04"),
    ("MAR-23", "2023-03"),
    ("Mar-2010", "2010-03"),
    ("2023-03", "2023-03"),
    ("2023-04", "2023-04"),
    ("garbage", "PARSE_ERROR"),
    ("", "PARSE_ERROR"),
    (None, "PARSE_ERROR"),
    (float("nan"), "PARSE_ERROR"),
]

TICKER_CASES = [
    (" TCS ", "TCS"),
    ("tcs", "TCS"),
    ("BAJAJ-AUTO", "BAJAJ-AUTO"),
    ("M&M", "M&M"),
    (" m&m ", "M&M"),
    ("hdfcbank", "HDFCBANK"),
    ("  RELIANCE  ", "RELIANCE"),
    ("LTIM", "LTIM"),
    ("", "MISSING"),
    ("   ", "MISSING"),
    (None, "MISSING"),
    (float("nan"), "MISSING"),
    ("icicibank", "ICICIBANK"),
    ("TCS\n", "TCS"),
    ("tata steel", "TATA STEEL"),
]


@pytest.mark.parametrize(("raw", "expected"), YEAR_CASES)
def test_normalize_year(raw: object, expected: str) -> None:
    assert normalize_year(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), TICKER_CASES)
def test_normalize_ticker(raw: object, expected: str) -> None:
    assert normalize_ticker(raw) == expected
