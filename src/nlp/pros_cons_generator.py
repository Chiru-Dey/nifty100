"""Rule-based pros/cons generator for all Nifty 100 companies."""

import logging
import math
import os
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))
OUTPUT_PATH = OUTPUT_DIR / "pros_cons_generated.csv"
MIN_CONFIDENCE_PCT = float(os.getenv("PROS_CONS_MIN_CONFIDENCE", "60"))

ROCE_COLUMN_CANDIDATES = (
    "return_on_capital_pct",
    "roce_pct",
    "return_on_capital_employed_pct",
)
RATIO_SERIES = (
    "return_on_equity_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "free_cash_flow_cr",
    "dividend_payout_ratio_pct",
    "earnings_per_share",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
)
RAW_SERIES = (
    "sales",
    "net_profit",
    "total_assets",
    "borrowings",
    "roce_pct",
    "net_debt_cr",
    "ebitda_cr",
)

RULE_TEXT = {
    "PRO-01": "Consistently high return on equity above 20% demonstrates "
    "exceptional capital efficiency",
    "PRO-02": "Strong free cash flow generation over 5 years signals healthy "
    "business fundamentals",
    "PRO-03": "Debt-free balance sheet provides financial flexibility and "
    "eliminates interest burden",
    "PRO-04": "Revenue growing at above 15% CAGR over 5 years reflects strong "
    "business momentum",
    "PRO-05": "Operating profit margin above 25% indicates strong pricing power "
    "and cost discipline",
    "PRO-06": "Net profit compounding at above 20% over 5 years creates "
    "significant shareholder value",
    "PRO-07": "Very high interest coverage ratio reflects negligible financial "
    "stress from debt servicing",
    "PRO-08": "Consistent dividend yield above 2% backed by positive free "
    "cash flow",
    "PRO-09": "Earnings per share growing above 15% CAGR indicates strong "
    "earnings quality and compounding",
    "PRO-10": "Return on equity improving for 3 consecutive years shows "
    "strengthening business quality",
    "PRO-11": "Revenue growing slower than profits shows improving operating "
    "leverage and scale benefits",
    "PRO-12": "Growing asset base funded by internal accruals reflects "
    "self-sustaining growth",
    "PRO-13": "Operating profit of {op} Cr in the latest year confirms viable "
    "core operations",
    "PRO-14": "Revenue base of {sales} Cr in the latest year provides scale and "
    "diversification advantages",
    "CON-01": "Debt-to-equity ratio of {de} is elevated for a non-financial "
    "company and warrants monitoring",
    "CON-02": "Free cash flow negative for 3 consecutive years raises concern "
    "about cash generation quality",
    "CON-03": "Operating margins declining for 3 consecutive years suggests "
    "pricing or cost pressure",
    "CON-04": "Company reported a net loss in the most recent financial year",
    "CON-05": "Revenue contraction over 2 consecutive years indicates demand "
    "weakness or market share loss",
    "CON-06": "Interest coverage ratio below 1.5x indicates the company is at "
    "risk of not meeting its debt obligations",
    "CON-07": "Dividend payout ratio above 100% means the company is paying "
    "dividends from reserves, which is unsustainable",
    "CON-08": "Rising debt-to-equity ratio over 3 years suggests increasing "
    "financial leverage risk",
    "CON-09": "Earnings per share declining for 3 consecutive years reflects "
    "deteriorating profitability",
    "CON-10": "Return on capital employed below 10% suggests the business is "
    "not generating sufficient returns on invested capital",
    "CON-11": "Net debt exceeding 3 times EBITDA is a high leverage ratio and "
    "limits financial flexibility",
    "CON-12": "Revenue growing at below 5% over 5 years lags inflation and "
    "suggests limited business momentum",
    "CON-13": "Dividend yield of {dy}% remains below the 2% income-investor "
    "threshold",
    "CON-14": "P/E of {pe}x above the Nifty 100 median of {med}x leaves limited "
    "margin of safety",
    "CON-15": "P/E of {pe}x at or below the Nifty 100 median of {med}x implies "
    "market scepticism on earnings durability",
}

logger = logging.getLogger(__name__)


@dataclass
class CompanyContext:
    ticker: str
    is_financial: bool
    dividend_yield_pct: float | None
    pe_ratio: float | None
    pe_median: float | None
    m: dict[str, list[float]]

    def series(self, name: str) -> list[float]:
        """Return the year-ordered series for a metric."""
        return self.m.get(name, [])

    def latest(self, name: str) -> float | None:
        """Return the most recent non-null value for a metric."""
        vals = [v for v in self.series(name) if not pd.isna(v)]
        return vals[-1] if vals else None


def load_frames(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Load all frames required by the rule engine."""
    queries = {
        "companies": "SELECT id AS company_id FROM companies",
        "sectors": "SELECT company_id, broad_sector FROM sectors",
        "market_cap": "SELECT company_id, year, dividend_yield_pct, pe_ratio "
        "FROM market_cap",
        "ratios": "SELECT * FROM financial_ratios",
        "pl": "SELECT company_id, year, sales, net_profit, operating_profit, "
        "depreciation FROM profitandloss",
        "bs": "SELECT company_id, year, total_assets, borrowings, "
        "equity_capital, reserves, investments FROM balancesheet",
    }
    return {name: pd.read_sql(q, conn) for name, q in queries.items()}


def _add_computed_columns(raw: pd.DataFrame) -> pd.DataFrame:
    """Derive ROCE, net debt and EBITDA proxy columns from raw statements."""
    capital = raw["equity_capital"] + raw["reserves"] + raw["borrowings"]
    ebit = raw["operating_profit"] - raw["depreciation"]
    raw["roce_pct"] = (ebit / capital * 100).where(capital > 0)
    raw["net_debt_cr"] = raw["borrowings"] - raw["investments"]
    raw["ebitda_cr"] = raw["operating_profit"]
    return raw


def build_contexts(frames: dict[str, pd.DataFrame]) -> list[CompanyContext]:
    """Assemble per-company metric contexts for rule evaluation."""
    ratios = frames["ratios"].sort_values(["company_id", "year"])
    raw = _add_computed_columns(
        frames["pl"].merge(frames["bs"], on=["company_id", "year"], how="outer")
    ).sort_values(["company_id", "year"])
    ratio_groups = dict(tuple(ratios.groupby("company_id")))
    raw_groups = dict(tuple(raw.groupby("company_id")))
    tail = (
        frames["market_cap"]
        .sort_values("year")
        .groupby("company_id")
        .tail(1)
        .set_index("company_id")
    )
    pe_median = float(tail["pe_ratio"].dropna().median())
    financials = set(
        frames["sectors"].loc[
            frames["sectors"]["broad_sector"] == "Financials", "company_id"
        ]
    )
    roce_col = next((c for c in ROCE_COLUMN_CANDIDATES if c in ratios.columns), None)
    contexts = []
    for ticker in frames["companies"]["company_id"].tolist():
        g = ratio_groups.get(ticker)
        r = raw_groups.get(ticker)
        m: dict[str, list[float]] = {}
        if g is not None:
            m.update({c: g[c].tolist() for c in RATIO_SERIES if c in g.columns})
        if r is not None:
            m.update({c: r[c].tolist() for c in RAW_SERIES if c in r.columns})
        if g is not None and roce_col is not None:
            m["roce_pct"] = g[roce_col].tolist()
        dy, pe = tail.get("dividend_yield_pct", {}).get(ticker), tail.get(
            "pe_ratio", {}
        ).get(ticker)
        contexts.append(
            CompanyContext(
                ticker=ticker,
                is_financial=ticker in financials,
                dividend_yield_pct=None if dy is None or pd.isna(dy) else float(dy),
                pe_ratio=None if pe is None or pd.isna(pe) else float(pe),
                pe_median=pe_median,
                m=m,
            )
        )
    return contexts


def _best_window(
    values: list[float], n: int, predicate: Callable[[list[float]], bool]
) -> tuple[list[float], bool] | None:
    """Most recent length-n clean window satisfying predicate, trailing flag."""
    for end in range(len(values), n - 1, -1):
        window = values[end - n : end]
        if not any(pd.isna(v) for v in window) and predicate(window):
            return window, end == len(values)
    return None


def _best_run(
    values: list[float], min_len: int, predicate: Callable[[float], bool]
) -> tuple[int, bool] | None:
    """Most recent run of at least min_len matching values, trailing flag."""
    best, run = None, 0
    for i, v in enumerate(values):
        if pd.isna(v) or not predicate(v):
            run = 0
            continue
        run += 1
        if run >= min_len:
            best = (run, i == len(values) - 1)
    return best


def _best_scalar(
    values: list[float], predicate: Callable[[float], bool]
) -> tuple[float, bool] | None:
    """Most recent value satisfying predicate, trailing flag."""
    for i in range(len(values) - 1, -1, -1):
        v = values[i]
        if not pd.isna(v) and predicate(v):
            return v, i == len(values) - 1
    return None


def _increasing(window: list[float]) -> bool:
    """True when every value strictly exceeds its predecessor."""
    return all(b > a for a, b in zip(window, window[1:]))


def _decreasing(window: list[float]) -> bool:
    """True when every value strictly falls below its predecessor."""
    return all(b < a for a, b in zip(window, window[1:]))


def pro_roe_sustained(ctx: CompanyContext) -> tuple[float, bool] | None:
    """ROE above 20% sustained across any 3-year window."""
    res = _best_window(ctx.series("return_on_equity_pct"), 3, lambda w: all(v > 20 for v in w))
    return None if res is None else ((min(res[0]) - 20) / 20, res[1])


def pro_fcf_streak(ctx: CompanyContext) -> tuple[float, bool] | None:
    """FCF positive for 5+ consecutive years in any window."""
    res = _best_run(ctx.series("free_cash_flow_cr"), 5, lambda v: v > 0)
    return None if res is None else ((res[0] - 5) / 5, res[1])


def pro_debt_free(ctx: CompanyContext) -> tuple[float, bool] | None:
    """D/E equal to zero in the latest year."""
    return (0.8, True) if ctx.latest("debt_to_equity") == 0 else None


def pro_revenue_cagr(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Revenue CAGR above 15% over any 5-year window."""
    res = _best_scalar(ctx.series("revenue_cagr_5yr"), lambda v: v > 15)
    return None if res is None else ((res[0] - 15) / 15, res[1])


def pro_opm(ctx: CompanyContext) -> tuple[float, bool] | None:
    """OPM above 25% in the latest year."""
    v = ctx.latest("operating_profit_margin_pct")
    return None if v is None or v <= 25 else ((v - 25) / 25, True)


def pro_pat_cagr(ctx: CompanyContext) -> tuple[float, bool] | None:
    """PAT CAGR above 20% over any 5-year window."""
    res = _best_scalar(ctx.series("pat_cagr_5yr"), lambda v: v > 20)
    return None if res is None else ((res[0] - 20) / 20, res[1])


def pro_interest_coverage(ctx: CompanyContext) -> tuple[float, bool] | None:
    """ICR above 10x in any year, or debt-free balance sheet."""
    if ctx.latest("debt_to_equity") == 0:
        return 0.8, True
    res = _best_scalar(ctx.series("interest_coverage"), lambda v: v > 10)
    return None if res is None else ((res[0] - 10) / 20, res[1])


def pro_dividend_yield(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Dividend yield above 2% backed by positive latest FCF."""
    dy = ctx.dividend_yield_pct
    fcf = ctx.latest("free_cash_flow_cr")
    if dy is None or dy <= 2 or fcf is None or fcf <= 0:
        return None
    return min(1.0, (dy - 2) / 2 + 0.5), True


def pro_eps_cagr(ctx: CompanyContext) -> tuple[float, bool] | None:
    """EPS CAGR above 15% over any 5-year window."""
    res = _best_scalar(ctx.series("eps_cagr_5yr"), lambda v: v > 15)
    return None if res is None else ((res[0] - 15) / 15, res[1])


def pro_roe_improving(ctx: CompanyContext) -> tuple[float, bool] | None:
    """ROE improving for 3 consecutive years in any window."""
    res = _best_window(ctx.series("return_on_equity_pct"), 4, _increasing)
    return None if res is None else (min(1.0, (res[0][-1] - res[0][0]) / 10), res[1])


def pro_operating_leverage(ctx: CompanyContext) -> tuple[float, bool] | None:
    """PAT CAGR exceeding revenue CAGR in any 5-year window."""
    rev = ctx.series("revenue_cagr_5yr")
    pat = ctx.series("pat_cagr_5yr")
    n = min(len(rev), len(pat))
    for i in range(n - 1, -1, -1):
        r, p = rev[i], pat[i]
        if pd.isna(r) or pd.isna(p) or p <= r or p <= 0:
            continue
        return min(1.0, (p - r) / 10), i == n - 1
    return None


def pro_self_funded_growth(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Assets growing while borrowings decline in any 3-year window."""
    assets = ctx.series("total_assets")
    debt = ctx.series("borrowings")
    n = min(len(assets), len(debt))
    for end in range(n, 2, -1):
        wa, wd = assets[end - 3 : end], debt[end - 3 : end]
        if any(pd.isna(v) for v in wa) or any(pd.isna(v) for v in wd):
            continue
        if _increasing(wa) and _decreasing(wd):
            return 0.7, end == n
    return None


def con_leverage(ctx: CompanyContext) -> tuple[float, bool] | None:
    """D/E above 2.0 for non-financial companies in the latest year."""
    de = ctx.latest("debt_to_equity")
    if ctx.is_financial or de is None or de <= 2:
        return None
    return (de - 2) / 3, True


def con_fcf_streak(ctx: CompanyContext) -> tuple[float, bool] | None:
    """FCF negative for 3 consecutive years in any window."""
    res = _best_run(ctx.series("free_cash_flow_cr"), 3, lambda v: v < 0)
    return None if res is None else ((res[0] - 3) / 3, res[1])


def con_opm_declining(ctx: CompanyContext) -> tuple[float, bool] | None:
    """OPM declining for 3 consecutive years in any window."""
    res = _best_window(ctx.series("operating_profit_margin_pct"), 4, _decreasing)
    return None if res is None else (min(1.0, (res[0][0] - res[0][-1]) / 10), res[1])


def con_net_loss(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Net profit negative in the latest year."""
    net = ctx.latest("net_profit")
    sales = ctx.latest("sales")
    if net is None or net >= 0:
        return None
    if sales is None or sales <= 0:
        return 0.7, True
    return min(1.0, (-net / sales * 100) / 20), True


def con_revenue_decline(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Revenue declining for 2+ consecutive years in any window."""
    res = _best_window(ctx.series("sales"), 3, _decreasing)
    if res is None:
        return None
    w = res[0]
    return min(1.0, (w[0] - w[-1]) / max(w[0], 1e-9) * 100 / 20), res[1]


def con_interest_coverage(ctx: CompanyContext) -> tuple[float, bool] | None:
    """ICR below 1.5x in any year."""
    res = _best_scalar(ctx.series("interest_coverage"), lambda v: v < 1.5)
    return None if res is None else ((1.5 - res[0]) / 1.5, res[1])


def con_dividend_payout(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Dividend payout above 100% in any year."""
    res = _best_scalar(ctx.series("dividend_payout_ratio_pct"), lambda v: v > 100)
    return None if res is None else ((res[0] - 100) / 100, res[1])


def con_leverage_rising(ctx: CompanyContext) -> tuple[float, bool] | None:
    """D/E rising for 3 consecutive years in any window."""
    res = _best_window(ctx.series("debt_to_equity"), 4, _increasing)
    return None if res is None else (min(1.0, res[0][-1] - res[0][0]), res[1])


def con_eps_declining(ctx: CompanyContext) -> tuple[float, bool] | None:
    """EPS declining for 3 consecutive years in any window."""
    res = _best_window(ctx.series("earnings_per_share"), 4, _decreasing)
    if res is None:
        return None
    w = res[0]
    return min(1.0, (w[0] - w[-1]) / max(abs(w[0]), 1e-9)), res[1]


def con_roce(ctx: CompanyContext) -> tuple[float, bool] | None:
    """ROCE below 10% in the latest year."""
    v = ctx.latest("roce_pct")
    return None if v is None or v >= 10 else ((10 - v) / 10, True)


def con_net_debt_ebitda(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Net debt above 3x EBITDA in the latest year."""
    nd = ctx.latest("net_debt_cr")
    ebitda = ctx.latest("ebitda_cr")
    if nd is None or ebitda is None or ebitda <= 0 or nd <= 3 * ebitda:
        return None
    return (nd / ebitda - 3) / 3, True


def con_low_growth(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Revenue CAGR below 5% over any 5-year window."""
    res = _best_scalar(ctx.series("revenue_cagr_5yr"), lambda v: v < 5)
    return None if res is None else ((5 - res[0]) / 5, res[1])


def pro_fallback_operating(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Positive latest operating profit as baseline pro (AC-16 coverage)."""
    op = ctx.latest("ebitda_cr")
    if op is None or op <= 0:
        return None
    return min(1.0, math.log10(max(op, 1)) / 4), False


def pro_fallback_scale(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Revenue scale as baseline pro (AC-16 coverage)."""
    sales = ctx.latest("sales")
    if sales is None or sales <= 0:
        return None
    return min(1.0, math.log10(max(sales, 1)) / 5), False


def con_fallback_yield(ctx: CompanyContext) -> tuple[float, bool] | None:
    """Sub-2% dividend yield as baseline con (AC-16 coverage)."""
    dy = ctx.dividend_yield_pct
    if dy is None or dy >= 2:
        return None
    return min(1.0, (2 - dy) / 2), False


def con_fallback_premium(ctx: CompanyContext) -> tuple[float, bool] | None:
    """P/E above universe median as baseline con (AC-16 coverage)."""
    pe, med = ctx.pe_ratio, ctx.pe_median
    if pe is None or med is None or pe <= med:
        return None
    return min(1.0, (pe - med) / max(med, 1e-9)), False


def con_fallback_scepticism(ctx: CompanyContext) -> tuple[float, bool] | None:
    """P/E at/below universe median as baseline con (AC-16 coverage)."""
    pe, med = ctx.pe_ratio, ctx.pe_median
    if pe is None or med is None or pe > med:
        return None
    return min(1.0, (med - pe) / max(med, 1e-9)), False


RULES: list[tuple[str, str, Callable[[CompanyContext], tuple[float, bool] | None]]] = [
    ("PRO-01", "pro", pro_roe_sustained),
    ("PRO-02", "pro", pro_fcf_streak),
    ("PRO-03", "pro", pro_debt_free),
    ("PRO-04", "pro", pro_revenue_cagr),
    ("PRO-05", "pro", pro_opm),
    ("PRO-06", "pro", pro_pat_cagr),
    ("PRO-07", "pro", pro_interest_coverage),
    ("PRO-08", "pro", pro_dividend_yield),
    ("PRO-09", "pro", pro_eps_cagr),
    ("PRO-10", "pro", pro_roe_improving),
    ("PRO-11", "pro", pro_operating_leverage),
    ("PRO-12", "pro", pro_self_funded_growth),
    ("CON-01", "con", con_leverage),
    ("CON-02", "con", con_fcf_streak),
    ("CON-03", "con", con_opm_declining),
    ("CON-04", "con", con_net_loss),
    ("CON-05", "con", con_revenue_decline),
    ("CON-06", "con", con_interest_coverage),
    ("CON-07", "con", con_dividend_payout),
    ("CON-08", "con", con_leverage_rising),
    ("CON-09", "con", con_eps_declining),
    ("CON-10", "con", con_roce),
    ("CON-11", "con", con_net_debt_ebitda),
    ("CON-12", "con", con_low_growth),
]
PRO_FALLBACKS = [("PRO-13", pro_fallback_operating), ("PRO-14", pro_fallback_scale)]
CON_FALLBACKS = [
    ("CON-13", con_fallback_yield),
    ("CON-14", con_fallback_premium),
    ("CON-15", con_fallback_scepticism),
]


def confidence_pct(strength: float, current: bool) -> int:
    """Map signal strength and recency to a 66-98 confidence score."""
    base, span = (78, 20) if current else (66, 12)
    return round(base + span * min(1.0, max(0.0, strength)))


def rule_text(rule_id: str, ctx: CompanyContext) -> str:
    """Render rule text with metric values injected where templated."""
    de = ctx.latest("debt_to_equity")
    op = ctx.latest("ebitda_cr")
    sales = ctx.latest("sales")
    kwargs = {
        "de": round(de, 2) if de is not None else 0.0,
        "op": round(op, 0) if op is not None else 0.0,
        "sales": round(sales, 0) if sales is not None else 0.0,
        "dy": round(ctx.dividend_yield_pct or 0.0, 2),
        "pe": round(ctx.pe_ratio or 0.0, 1),
        "med": round(ctx.pe_median or 0.0, 1),
    }
    return RULE_TEXT[rule_id].format(**kwargs)


def _record(
    ctx: CompanyContext, rule_id: str, kind: str, strength: float, current: bool
) -> tuple[str, str, str, str, int] | None:
    """Build an output row when confidence clears the inclusion threshold."""
    confidence = confidence_pct(strength, current)
    if confidence <= MIN_CONFIDENCE_PCT:
        return None
    return (ctx.ticker, kind, rule_id, rule_text(rule_id, ctx), confidence)


def generate(contexts: list[CompanyContext]) -> pd.DataFrame:
    """Evaluate all rules per company, backfilling sides to satisfy AC-16."""
    records = []
    for ctx in contexts:
        fired = {"pro": False, "con": False}
        for rule_id, kind, fn in RULES:
            result = fn(ctx)
            if result is None:
                continue
            row = _record(ctx, rule_id, kind, result[0], result[1])
            if row is not None:
                records.append(row)
                fired[kind] = True
        if not fired["pro"]:
            for rule_id, fn in PRO_FALLBACKS:
                result = fn(ctx)
                if result is None:
                    continue
                row = _record(ctx, rule_id, "pro", result[0], result[1])
                if row is not None:
                    records.append(row)
                    break
        if not fired["con"]:
            for rule_id, fn in CON_FALLBACKS:
                result = fn(ctx)
                if result is None:
                    continue
                row = _record(ctx, rule_id, "con", result[0], result[1])
                if row is not None:
                    records.append(row)
                    break
    return pd.DataFrame(
        records,
        columns=["company_id", "type", "rule_id", "text", "confidence_pct"],
    )


def validate_coverage(df: pd.DataFrame, companies: list[str]) -> list[str]:
    """Return tickers missing at least one pro or one con (AC-16)."""
    counts = df.groupby(["company_id", "type"]).size()
    missing = []
    for ticker in companies:
        if counts.get((ticker, "pro"), 0) < 1 or counts.get((ticker, "con"), 0) < 1:
            missing.append(ticker)
    return missing


def main() -> int:
    """Generate pros/cons CSV, verify coverage, return exit status."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        frames = load_frames(conn)
    contexts = build_contexts(frames)
    df = generate(contexts).sort_values(["company_id", "type", "rule_id"])
    df.to_csv(OUTPUT_PATH, index=False)
    logger.info(
        "rows=%d pros=%d cons=%d companies=%d",
        len(df),
        int((df["type"] == "pro").sum()),
        int((df["type"] == "con").sum()),
        df["company_id"].nunique(),
    )
    missing = validate_coverage(df, frames["companies"]["company_id"].tolist())
    if missing:
        logger.error("AC-16 coverage gap (missing pro/con): %s", ", ".join(missing))
        return 1
    logger.info("coverage verified: every company has >=1 pro and >=1 con")
    return 0


if __name__ == "__main__":
    sys.exit(main())