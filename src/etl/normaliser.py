import math
import re

MONTH_MAP = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

_YYYY_MM = re.compile(r"\d{4}-\d{2}")
_YYYY = re.compile(r"(?:fy)?(\d{4})", re.IGNORECASE)
_YY = re.compile(r"(?:fy)?(\d{2})", re.IGNORECASE)
_MON_YEAR = re.compile(r"([A-Za-z]+)[-\s]+(\d{2,4})")


def normalize_year(value: object) -> str:
    """Standardise financial-year labels to YYYY-MM, else PARSE_ERROR."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "PARSE_ERROR"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if _YYYY_MM.fullmatch(text):
        return text
    match = _YYYY.fullmatch(text) or _YY.fullmatch(text)
    if match:
        year = int(match.group(1))
        if year < 100:
            year += 2000
        return f"{year:04d}-03"
    match = _MON_YEAR.fullmatch(text)
    if match:
        month = MONTH_MAP.get(match.group(1).lower()[:3])
        if month:
            year = int(match.group(2))
            if year < 100:
                year += 2000
            return f"{year:04d}-{month}"
    return "PARSE_ERROR"


def normalize_ticker(value: object) -> str:
    """Normalise company identifiers to stripped uppercase tickers, else MISSING."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "MISSING"
    text = str(value).strip().upper()
    return text or "MISSING"
