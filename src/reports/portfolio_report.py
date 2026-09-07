"""Portfolio summary PDF: one page per company with KPI trend arrows."""

import logging
import os
import sqlite3
from pathlib import Path

import matplotlib
import pandas as pd
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "nifty100.db"))
REPORT_DIR = Path(
    os.getenv("PORTFOLIO_REPORT_DIR", BASE_DIR / "reports" / "portfolio")
)

UW = 16.6 * cm
NAVY = colors.HexColor("#002060")
LIGHT = colors.HexColor("#EEF1F6")
FLAT_TOLERANCE_PCT = float(os.getenv("TREND_FLAT_TOLERANCE_PCT", "2.0"))

ROCE_CANDIDATES = (
    "return_on_capital_pct",
    "roce_pct",
    "return_on_capital_employed_pct",
)
METRICS = (
    ("roe_pct", "ROE %", True),
    ("roce_pct", "ROCE %", True),
    ("npm_pct", "Net Margin %", True),
    ("debt_to_equity", "D/E", False),
    ("revenue_cagr_5yr", "Rev CAGR 5Y %", True),
    ("free_cash_flow_cr", "FCF (Cr)", True),
)

_FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
pdfmetrics.registerFont(TTFont("DejaVu", str(_FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(
    TTFont("DejaVu-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))
)

logger = logging.getLogger(__name__)
_base = getSampleStyleSheet()
CELL_STYLE = ParagraphStyle(
    "cell", parent=_base["Normal"], fontName="DejaVu", fontSize=9, leading=12,
    wordWrap="CJK",
)
HEADER_CELL_STYLE = ParagraphStyle(
    "hcell", parent=CELL_STYLE, fontName="DejaVu-Bold", textColor=colors.white,
)
TITLE_STYLE = ParagraphStyle(
    "title", parent=CELL_STYLE, fontName="DejaVu-Bold", fontSize=13, leading=16,
    textColor=colors.white,
)
ARROW_STYLE = ParagraphStyle(
    "arrow", parent=CELL_STYLE, fontSize=12, leading=14, alignment=TA_CENTER,
)


def _clip(text: object, limit: int = 200) -> str:
    """Escape XML and truncate long text with ellipsis per R-08."""
    clean = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _fmt(value: float | None) -> str:
    """Format a KPI value for table cells."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.1f}"


def fetch_companies(conn: sqlite3.Connection) -> pd.DataFrame:
    """Latest two ratio years per company with name and sector tags."""
    ratios = pd.read_sql("SELECT * FROM financial_ratios", conn)
    ratios = (
        ratios.sort_values(["company_id", "year"])
        .groupby("company_id", sort=True)
        .tail(2)
    )
    df = pd.read_sql(
        "SELECT c.id AS company_id, c.company_name, s.broad_sector "
        "FROM companies c JOIN sectors s ON s.company_id = c.id",
        conn,
    )
    df = df.merge(ratios, on="company_id", how="left")
    df["roe_pct"] = df["return_on_equity_pct"]
    df["npm_pct"] = df["net_profit_margin_pct"]
    roce_col = next((c for c in ROCE_CANDIDATES if c in df.columns), None)
    df["roce_pct"] = df[roce_col] if roce_col else None
    return df.sort_values(["company_id", "year"])


def _pair(group: pd.DataFrame) -> tuple[pd.Series | None, pd.Series | None]:
    """Return (latest, previous) ratio rows for one company."""
    group = group.dropna(subset=["year"])
    if not len(group):
        return None, None
    if len(group) == 1:
        return group.iloc[-1], None
    return group.iloc[-1], group.iloc[-2]


def trend_arrow(
    curr: float | None, prev: float | None, higher_better: bool
) -> tuple[str, str]:
    """Return (arrow glyph, YoY change text); flat band is +/-2%."""
    if curr is None or prev is None or pd.isna(curr) or pd.isna(prev):
        return "—", "N/A"
    if prev:
        change = (curr - prev) / abs(prev) * 100
        change_txt = f"{change:+,.1f}%"
        if abs(change) <= FLAT_TOLERANCE_PCT:
            return "→", change_txt
    else:
        change_txt = "N/A"
    improved = curr > prev if higher_better else curr < prev
    return ("↑" if improved else "↓"), change_txt


def build_story(df: pd.DataFrame) -> list:
    """Assemble one page per company in alphabetical ticker order."""
    story: list = []
    tickers = sorted(df["company_id"].unique())
    for i, ticker in enumerate(tickers):
        group = df[df["company_id"] == ticker]
        meta = group.iloc[0]
        curr, prev = _pair(group)
        header = Table(
            [[Paragraph(
                f"<b>{_clip(meta['company_name'])}</b> ({ticker}) — "
                f"{_clip(meta['broad_sector'])}",
                TITLE_STYLE,
            )]],
            colWidths=[UW],
        )
        header.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(header)
        story.append(Spacer(1, 0.4 * cm))
        rows = [[Paragraph(f"<b>{h}</b>", HEADER_CELL_STYLE)
                 for h in ("KPI", "Latest", "Previous", "YoY Change", "Trend")]]
        for col, label, higher_better in METRICS:
            c = None if curr is None else curr.get(col)
            p = None if prev is None else prev.get(col)
            arrow, change_txt = trend_arrow(c, p, higher_better)
            rows.append([
                Paragraph(label, CELL_STYLE),
                Paragraph(_fmt(c), CELL_STYLE),
                Paragraph(_fmt(p), CELL_STYLE),
                Paragraph(change_txt, CELL_STYLE),
                Paragraph(arrow, ARROW_STYLE),
            ])
        table = Table(
            rows,
            colWidths=[UW * 0.34, UW * 0.17, UW * 0.17, UW * 0.17, UW * 0.15],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        if i < len(tickers) - 1:
            story.append(PageBreak())
    return story


def generate(path: Path, story: list) -> int:
    """Build the portfolio PDF and return the rendered page count."""
    margin = (21 * cm - UW) / 2
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Nifty 100 portfolio summary",
    )
    doc.build(story)
    return doc.page


def main() -> int:
    """Generate reports/portfolio/portfolio_summary.pdf for all companies."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        df = fetch_companies(conn)
    path = REPORT_DIR / "portfolio_summary.pdf"
    pages = generate(path, build_story(df))
    companies = df["company_id"].nunique()
    logger.info(
        "portfolio pages=%d companies=%d size=%dKB",
        pages,
        companies,
        path.stat().st_size // 1024,
    )
    if pages != companies:
        logger.warning("page count %d != company count %d", pages, companies)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())