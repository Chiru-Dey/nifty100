"""CAGR engine for the Nifty 100 platform."""

import logging

import pandas as pd

from src.analytics.ratios import load_inputs, save_ratios

logger = logging.getLogger(__name__)

METRICS = {"revenue": "sales", "pat": "net_profit", "eps": "eps"}
WINDOWS = (3, 5, 10)

CAGR_COLUMNS = {
    f"{metric}_cagr_{window}yr{suffix}": dtype
    for metric in METRICS
    for window in WINDOWS
    for suffix, dtype in (("", "REAL"), ("_flag", "TEXT"))
}


def _num(value: float | None) -> float | None:
    """Return None for missing values else float."""
    return None if pd.isna(value) else float(value)


def _lookback(year: str, window: int) -> str:
    """Return the YYYY-MM label window years before year."""
    return f"{int(year[:4]) - window}{year[4:]}"


def cagr(
    base: float | None, end: float | None, window: int
) -> tuple[float | None, str | None]:
    """Compound annual growth rate percent with edge-case flag."""
    base_ = _num(base)
    end_ = _num(end)
    if base_ is None or end_ is None:
        return None, "INSUFFICIENT"
    if base_ == 0:
        return None, "ZERO_BASE"
    if base_ > 0 and end_ > 0:
        return ((end_ / base_) ** (1 / window) - 1) * 100, None
    if base_ > 0:
        return None, "DECLINE_TO_LOSS"
    if end_ > 0:
        return None, "TURNAROUND"
    return None, "BOTH_NEGATIVE"


def compute_cagr(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 3/5/10-year CAGR and flag columns for revenue, PAT, EPS."""
    rows = list(df.itertuples())
    lookup = {(r.company_id, r.year): r for r in rows}
    out = df[["company_id", "year"]].copy()
    for metric, column in METRICS.items():
        for window in WINDOWS:
            results = []
            for row in rows:
                base_row = lookup.get((row.company_id, _lookback(row.year, window)))
                base = None if base_row is None else getattr(base_row, column)
                value, flag = cagr(base, getattr(row, column), window)
                if flag not in (None, "INSUFFICIENT"):
                    logger.info(
                        "CAGR edge %s %s %s_%dyr: %s",
                        row.company_id,
                        row.year,
                        metric,
                        window,
                        flag,
                    )
                results.append((value, flag))
            out[f"{metric}_cagr_{window}yr"] = [v for v, _ in results]
            out[f"{metric}_cagr_{window}yr_flag"] = [f for _, f in results]
    return out


def main() -> None:
    """Run the Day 10 CAGR pipeline."""
    logging.basicConfig(level=logging.INFO)
    frame = compute_cagr(load_inputs())
    save_ratios(frame, CAGR_COLUMNS)
    logger.info("Computed %d CAGR rows", len(frame))


if __name__ == "__main__":
    main()