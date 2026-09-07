"""Two-page company tearsheet PDF generator (ReportLab + matplotlib)."""

import argparse
import logging
import os
import sqlite3
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

matplotlib.use("Agg")

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
REPORT_DIR = Path(os.getenv("REPORT_DIR", BASE_DIR / "reports" / "tearsheets"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", BASE_DIR / "output"))

UW = 16.6 * cm
MIN_HISTORY_YEARS = 3
NAVY = colors.HexColor("#002060")
GREEN = colors.HexColor("#1E7B34")
RED = colors.HexColor("#B3261E")
AMBER = colors.HexColor("#B26A00")
LIGHT = colors.HexColor("#EEF1F6")

TEST_TICKERS = ("TCS", "HDFCBANK", "RELIANCE", "SUNPHARMA", "TATASTEEL")

logger = logging.getLogger(__name__)
_base = getSampleStyleSheet()
CELL_STYLE = ParagraphStyle(
    "cell", parent=_base["Normal"], wordWrap="CJK", alignment=TA_CENTER,
    fontSize=9, leading=12,
)
TILE_STYLE = ParagraphStyle("tile", parent=CELL_STYLE, fontSize=10, leading=13)
HEADER_STYLE = ParagraphStyle(
    "header", parent=CELL_STYLE, fontSize=13, leading=16, textColor=colors.white,
)
BADGE_STYLE = ParagraphStyle(
    "badge", parent=CELL_STYLE, fontSize=10, leading=13, textColor=colors.white,
)
BULLET_STYLE = ParagraphStyle(
    "bullet", parent=_base["Normal"], wordWrap="CJK", fontSize=9, leading=12,
)
SECTION_STYLE = ParagraphStyle(
    "section", parent=_base["Normal"], fontSize=11, leading=14, textColor=NAVY,
    spaceBefore=6,
)


@dataclass
class CompanyData:
    ticker: str
    name: str
    sector: str
    sub_sector: str
    pl: pd.DataFrame
    bs: pd.DataFrame
    cf: pd.DataFrame
    metrics: pd.DataFrame
    kpis: dict[str, str]
    pros: list[str]
    cons: list[str]
    allocation_label: str


def _clip(text: object, limit: int = 200) -> str:
    """Escape XML and truncate long text with ellipsis per R-08."""
    clean = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _fmt(value: float | None, suffix: str = "") -> str:
    """Format a KPI value for tile display."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.1f}{suffix}"


def _pros_cons(ticker: str) -> tuple[list[str], list[str]]:
    """Load top auto-generated pros and cons for a company."""
    path = OUTPUT_DIR / "pros_cons_generated.csv"
    if not path.exists():
        return [], []
    df = pd.read_csv(path, dtype={"company_id": str})
    df = df[df["company_id"] == ticker].sort_values(
        "confidence_pct", ascending=False
    )
    pros = df.loc[df["type"] == "pro", "text"].head(4).tolist()
    cons = df.loc[df["type"] == "con", "text"].head(4).tolist()
    return pros, cons


def _allocation_label(ticker: str) -> str:
    """Latest capital allocation pattern label for a company."""
    path = OUTPUT_DIR / "capital_allocation.csv"
    if not path.exists():
        return "N/A"
    df = pd.read_csv(path, dtype={"company_id": str, "year": str})
    rows = df[df["company_id"] == ticker].sort_values("year")
    return str(rows.iloc[-1]["pattern_label"]) if len(rows) else "N/A"


def fetch_data(conn: sqlite3.Connection, ticker: str) -> CompanyData:
    """Load all tearsheet inputs for one company."""
    name = conn.execute(
        "SELECT company_name FROM companies WHERE id = ?", (ticker,)
    ).fetchone()
    sector = conn.execute(
        "SELECT broad_sector, sub_sector FROM sectors WHERE company_id = ?",
        (ticker,),
    ).fetchone()
    pl = pd.read_sql(
        "SELECT year, sales, net_profit, operating_profit, depreciation "
        "FROM profitandloss WHERE company_id = ? ORDER BY year",
        conn,
        params=(ticker,),
    )
    bs = pd.read_sql(
        "SELECT year, equity_capital, reserves, borrowings, other_liabilities "
        "FROM balancesheet WHERE company_id = ? ORDER BY year",
        conn,
        params=(ticker,),
    )
    cf = pd.read_sql(
        "SELECT year, operating_activity, investing_activity, "
        "financing_activity, net_cash_flow FROM cashflow "
        "WHERE company_id = ? ORDER BY year",
        conn,
        params=(ticker,),
    )
    metrics = pl.merge(bs, on="year", how="inner")
    equity = metrics["equity_capital"] + metrics["reserves"]
    capital = equity + metrics["borrowings"]
    ebit = metrics["operating_profit"] - metrics["depreciation"]
    metrics["roe_pct"] = (metrics["net_profit"] / equity * 100).where(equity > 0)
    metrics["roce_pct"] = (ebit / capital * 100).where(capital > 0)
    last = metrics.iloc[-1] if len(metrics) else None
    de = (
        last["borrowings"] / (last["equity_capital"] + last["reserves"])
        if last is not None and (last["equity_capital"] + last["reserves"]) > 0
        else None
    )
    npm = (
        last["net_profit"] / last["sales"] * 100
        if last is not None and last["sales"]
        else None
    )
    cagr = conn.execute(
        "SELECT revenue_cagr_5yr FROM financial_ratios WHERE company_id = ? "
        "ORDER BY year DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    pe = conn.execute(
        "SELECT pe_ratio FROM market_cap WHERE company_id = ? "
        "ORDER BY year DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    kpis = {
        "ROE %": _fmt(None if last is None else last["roe_pct"]),
        "ROCE %": _fmt(None if last is None else last["roce_pct"]),
        "Net Margin %": _fmt(npm),
        "D/E": _fmt(de, "x"),
        "Rev CAGR 5Y %": _fmt(None if not cagr else cagr[0]),
        "P/E": _fmt(None if not pe else pe[0]),
    }
    pros, cons = _pros_cons(ticker)
    return CompanyData(
        ticker=ticker,
        name=str(name[0]) if name else ticker,
        sector=str(sector[0]) if sector else "N/A",
        sub_sector=str(sector[1]) if sector else "N/A",
        pl=pl,
        bs=bs,
        cf=cf,
        metrics=metrics,
        kpis=kpis,
        pros=pros,
        cons=cons,
        allocation_label=_allocation_label(ticker),
    )


def _figure_to_image(fig: plt.Figure, height_cm: float) -> Image:
    """Render a matplotlib figure to a ReportLab image flowable."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=UW, height=height_cm * cm)


def _empty_figure(message: str, height_cm: float) -> Image:
    """Placeholder image when a company lacks the underlying data."""
    fig, ax = plt.subplots(figsize=(6.54, height_cm / 2.54))
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=8)
    ax.axis("off")
    fig.tight_layout()
    return _figure_to_image(fig, height_cm)


def _fy_labels(years: pd.Series) -> list[str]:
    """Convert YYYY-MM year strings to short FY labels."""
    return [f"FY{str(y)[2:4]}" for y in years]


def chart_revenue_profit(pl: pd.DataFrame) -> Image:
    """10-year revenue and net profit bar charts side by side."""
    if not len(pl):
        return _empty_figure("No P&L data", 7.5)
    data = pl.tail(10)
    labels = _fy_labels(data["year"])
    fig, axes = plt.subplots(1, 2, figsize=(6.54, 7.5 / 2.54))
    axes[0].bar(labels, data["sales"], color="#002060")
    axes[0].set_title("Revenue (Cr)", fontsize=8)
    axes[1].bar(labels, data["net_profit"], color="#4C72B0")
    axes[1].set_title("Net Profit (Cr)", fontsize=8)
    for ax in axes:
        ax.tick_params(labelsize=6, rotation=45)
    fig.tight_layout()
    return _figure_to_image(fig, 7.5)


def chart_roe_roce(metrics: pd.DataFrame) -> Image:
    """ROE and ROCE dual-axis line chart over the last 10 years."""
    if not len(metrics):
        return _empty_figure("No ratio history", 7.5)
    data = metrics.tail(10)
    labels = _fy_labels(data["year"])
    fig, ax1 = plt.subplots(figsize=(6.54, 7.5 / 2.54))
    ax1.plot(labels, data["roe_pct"], marker="o", color="#002060", label="ROE %")
    ax1.set_ylabel("ROE %", fontsize=7)
    ax2 = ax1.twinx()
    ax2.plot(labels, data["roce_pct"], marker="s", color="#B26A00", label="ROCE %")
    ax2.set_ylabel("ROCE %", fontsize=7)
    handles, labels_l = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(handles + h2, labels_l + l2, fontsize=6, loc="upper left")
    ax1.set_title("ROE vs ROCE trend", fontsize=8)
    ax1.tick_params(labelsize=6, rotation=45)
    fig.tight_layout()
    return _figure_to_image(fig, 7.5)


def chart_balance_sheet(bs: pd.DataFrame) -> Image:
    """Balance sheet composition stacked bar by year."""
    if not len(bs):
        return _empty_figure("No balance sheet data", 8)
    data = bs.tail(10)
    labels = _fy_labels(data["year"])
    equity = data["equity_capital"] + data["reserves"]
    fig, ax = plt.subplots(figsize=(6.54, 8 / 2.54))
    ax.bar(labels, equity, color="#1E7B34", label="Equity")
    ax.bar(
        labels, data["borrowings"], bottom=equity, color="#B3261E",
        label="Borrowings",
    )
    ax.bar(
        labels, data["other_liabilities"], bottom=equity + data["borrowings"],
        color="#4C72B0", label="Other Liabilities",
    )
    ax.legend(fontsize=6)
    ax.set_title("Balance Sheet composition (Cr)", fontsize=8)
    ax.tick_params(labelsize=6, rotation=45)
    fig.tight_layout()
    return _figure_to_image(fig, 8)


def chart_cashflow_waterfall(cf: pd.DataFrame) -> Image:
    """Cash flow waterfall for the latest year (CFO, CFI, CFF, net)."""
    if not len(cf):
        return _empty_figure("No cash flow data", 7)
    row = cf.iloc[-1]
    steps = [
        row["operating_activity"],
        row["investing_activity"],
        row["financing_activity"],
    ]
    bottoms = [0, steps[0], steps[0] + steps[1]]
    net = row["net_cash_flow"]
    fig, ax = plt.subplots(figsize=(6.54, 7 / 2.54))
    for i, (val, base) in enumerate(zip(steps, bottoms)):
        ax.bar(i, val, bottom=base, color="#1E7B34" if val >= 0 else "#B3261E")
    ax.bar(3, net, color="#002060")
    ax.set_xticks(range(4))
    ax.set_xticklabels(["CFO", "CFI", "CFF", "Net Cash"], fontsize=7)
    ax.set_title(f"Cash Flow waterfall FY{str(row['year'])[2:4]} (Cr)", fontsize=8)
    ax.tick_params(labelsize=6)
    fig.tight_layout()
    return _figure_to_image(fig, 7)


def _badge_color(label: str) -> colors.Color:
    """Map capital allocation label to badge colour."""
    if label.startswith("Distress"):
        return RED
    if label.startswith(("Reinvestor", "Shareholder")):
        return GREEN
    return AMBER


def build_story(data: CompanyData) -> list:
    """Assemble the two-page tearsheet flowables."""
    story: list = []
    header = Table(
        [[Paragraph(
            f"<b>{_clip(data.name)}</b> ({data.ticker}) — {_clip(data.sector)}"
            f" / {_clip(data.sub_sector)}",
            HEADER_STYLE,
        )]],
        colWidths=[UW],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.35 * cm))
    items = list(data.kpis.items())
    cells = [Paragraph(f"<b>{v}</b><br/>{_clip(k)}", TILE_STYLE) for k, v in items]
    tiles = Table([cells[0:3], cells[3:6]], colWidths=[UW / 3] * 3)
    tiles.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tiles)
    story.append(Spacer(1, 0.35 * cm))
    story.append(chart_revenue_profit(data.pl))
    story.append(Spacer(1, 0.3 * cm))
    story.append(chart_roe_roce(data.metrics))
    story.append(PageBreak())
    story.append(
        Paragraph(f"{data.ticker} — Balance Sheet & Cash Flow", SECTION_STYLE)
    )
    story.append(chart_balance_sheet(data.bs))
    story.append(Spacer(1, 0.3 * cm))
    story.append(chart_cashflow_waterfall(data.cf))
    story.append(Paragraph("Pros", SECTION_STYLE))
    for text in data.pros or ["No recorded pros"]:
        story.append(
            Paragraph(
                f'<font color="#1E7B34">&#9679;</font> {_clip(text)}', BULLET_STYLE
            )
        )
    story.append(Paragraph("Cons", SECTION_STYLE))
    for text in data.cons or ["No recorded cons"]:
        story.append(
            Paragraph(
                f'<font color="#B3261E">&#9679;</font> {_clip(text)}', BULLET_STYLE
            )
        )
    story.append(Spacer(1, 0.3 * cm))
    badge = Table(
        [[Paragraph(
            f"<b>Capital Allocation: {_clip(data.allocation_label)}</b>",
            BADGE_STYLE,
        )]],
        colWidths=[UW],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _badge_color(data.allocation_label)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(badge)
    return story


def generate_tearsheet(data: CompanyData, path: Path) -> int:
    """Build the tearsheet PDF and return the rendered page count."""
    margin = (21 * cm - UW) / 2
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"{data.ticker} tearsheet",
    )
    doc.build(build_story(data))
    return doc.page


def company_history(conn: sqlite3.Connection) -> pd.DataFrame:
    """Distinct P&L year count per company."""
    return pd.read_sql(
        "SELECT company_id, COUNT(DISTINCT year) AS years FROM profitandloss "
        "GROUP BY company_id",
        conn,
    )


def run_batch(conn: sqlite3.Connection) -> int:
    """Generate tearsheets for all companies with 3+ years of history."""
    history = company_history(conn).set_index("company_id")["years"]
    tickers = pd.read_sql(
        "SELECT id AS company_id FROM companies", conn
    )["company_id"].tolist()
    skipped = []
    generated = 0
    for ticker in tickers:
        years = int(history.get(ticker, 0))
        if years < MIN_HISTORY_YEARS:
            skipped.append((ticker, years, "fewer than 3 years of history"))
            continue
        pages = generate_tearsheet(
            fetch_data(conn, ticker), REPORT_DIR / f"{ticker}_tearsheet.pdf"
        )
        generated += 1
        if pages != 2:
            logger.warning("%s expected 2 pages, rendered %d", ticker, pages)
    pd.DataFrame(skipped, columns=["company_id", "years", "reason"]).to_csv(
        OUTPUT_DIR / "skipped_tearsheets.csv", index=False
    )
    logger.info("tearsheets generated=%d skipped=%d", generated, len(skipped))
    return generated


def main() -> int:
    """Generate test tearsheets, or all tearsheets with --batch."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description="Company tearsheet generator")
    parser.add_argument("--batch", action="store_true", help="all 92 companies")
    args = parser.parse_args()
    with sqlite3.connect(DB_PATH) as conn:
        if args.batch:
            run_batch(conn)
            return 0
        env = os.getenv("TEARSHEET_TICKERS", ",".join(TEST_TICKERS))
        for ticker in [t.strip() for t in env.split(",")]:
            path = REPORT_DIR / f"{ticker}_tearsheet.pdf"
            pages = generate_tearsheet(fetch_data(conn, ticker), path)
            logger.info(
                "%s pages=%d size=%dKB",
                ticker,
                pages,
                path.stat().st_size // 1024,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())