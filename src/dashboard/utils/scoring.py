import pandas as pd


def _scale(s: pd.Series, higher_better: bool) -> pd.Series:
    """Scale a series to 0-100 using P10-P90 winsorisation."""
    lo, hi = s.quantile(0.1), s.quantile(0.9)
    if not pd.notna(lo) or not pd.notna(hi) or lo == hi:
        return pd.Series(50.0, index=s.index)
    scaled = (s.clip(lo, hi) - lo) / (hi - lo) * 100
    return scaled if higher_better else 100 - scaled


def composite_score(df: pd.DataFrame) -> pd.Series:
    """0-100 composite quality score per spec 25.1 weights."""
    specs = [
        ("return_on_equity_pct", 15, True),
        ("return_on_capital_pct", 10, True),
        ("net_profit_margin_pct", 10, True),
        ("free_cash_flow_cr", 15, True),
        ("revenue_cagr_5yr", 10, True),
        ("pat_cagr_5yr", 10, True),
        ("debt_to_equity", 15, False),
        ("interest_coverage", 5, True),
    ]
    score = pd.Series(0.0, index=df.index)
    total = 0
    for col, weight, higher_better in specs:
        if col not in df.columns:
            continue
        s = df[col]
        if col == "interest_coverage":
            s = s.fillna(s.max())
        score += weight * _scale(s, higher_better).fillna(50.0)
        total += weight
    return (score / total).round(1) if total else pd.Series(50.0, index=df.index)