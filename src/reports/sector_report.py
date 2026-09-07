"""Sector report PDF generator: median KPI summary and company metric table."""

import logging
import os
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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
REPORT_DIR = Path(os.getenv("SECTOR_REPORT_DIR", BASE_DIR / "reports" / "sector"))

UW = 16.6 * cm
NAVY = colors.HexColor("#002060")
LIGHT = colors.HexColor("#EEF1F6")

METRIC_COLUMNS = (
    ("roe_pct", "ROE %"),
    ("roce_pct", "ROCE %"),
    ("npm_pct", "NPM %"),
    ("debt_to_equity", "D/E"),
    ("revenue_cagr_5yr", "Rev CAGR 5Y %"),
    ("pat_cagr_5yr", "PAT CAGR 5Y %"),
    ("pe_ratio", "P/E"),
    ("dividend_yield_pct", "Div Yield %"),
)
ROCE_CANDIDATES = (
    "return_on_capital_pct",
    "roce_pct",
    "return_on_capital_employed_pct",
)

logger = logging.getLogger(__name__)
_base = getSampleStyleSheet()
CELL_STYLE = ParagraphStyle(
    "cell", parent=_base["Normal"], wordWrap="CJK", alignment=TA_CENTER,
    fontSize=7.5, leading=9.5,
)
HEADER_CELL_STYLE = ParagraphStyle(
    "hcell", parent=CELL_STYLE, fontSize=8, leading=10, textColor=colors.white,
)
TILE_STYLE = ParagraphStyle("tile", parent=CELL_STYLE, fontSize=9.5, leading=12)
TITLE_STYLE = ParagraphStyle(
    "title", parent=CELL_STYLE, fontSize=13, leading=16, textColor=colors.white,
)


def _fmt(value: float | None) -> str:
    """Format a metric value for table cells."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.1f}"


def fetch_sector_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    """Latest-year KPI frame for all companies with sector tags."""
    ratios = pd.read_sql("SELECT * FROM financial_ratios", conn)
    ratios = ratios.sort_values("year").groupby("company_id", sort=True).tail(1)
    market = pd.read_sql(
        "SELECT company_id, year, pe_ratio, dividend_yield_pct FROM market_cap",
        conn,
    )
    market = market.sort_values("year").groupby("company_id", sort=True).tail(1)
    df = pd.read_sql(
        "SELECT s.company_id, s.broad_sector, c.company_name FROM sectors s "
        "JOIN companies c ON c.id = s.company_id",
        conn,
    )
    df = df.merge(ratios, on="company_id", how="left")
    df = df.merge(
        market[["company_id", "pe_ratio", "dividend_yield_pct"]],
        on="company_id",
        how="left",
    )
    df["roe_pct"] = df["return_on_equity_pct"]
    df["npm_pct"] = df["net_profit_margin_pct"]
    roce_col = next((c for c in ROCE_CANDIDATES if c in ratios.columns), None)
    df["roce_pct"] = df[roce_col] if roce_col else None
    return df


def build_story(sector: str, df: pd.DataFrame) -> list:
    """Assemble the sector summary page and the company metric table."""
    story: list = []
    header = Table(
        [[Paragraph(f"<b>{sector} — Sector Report</b>", TITLE_STYLE)]],
        colWidths=[UW],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.35 * cm))
    medians = df[[col for col, _ in METRIC_COLUMNS]].median(numeric_only=True)
    tiles = [
        Paragraph(f"<b>{_fmt(medians.get(col))}</b><br/>{label}", TILE_STYLE)
        for col, label in METRIC_COLUMNS
    ]
    tile_table = Table([tiles[0:4], tiles[4:8]], colWidths=[UW / 4] * 4)
    tile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tile_table)
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            f"Companies covered: {len(df)} — sector medians on latest "
            "financial year per company",
            CELL_STYLE,
        )
    )
    story.append(PageBreak())
    rows = [
        [Paragraph("<b>Company</b>", HEADER_CELL_STYLE)]
        + [Paragraph(f"<b>{label}</b>", HEADER_CELL_STYLE)
           for _, label in METRIC_COLUMNS]
    ]
    for _, row in df.sort_values("company_id").iterrows():
        rows.append(
            [Paragraph(row["company_id"], CELL_STYLE)]
            + [Paragraph(_fmt(row.get(col)), CELL_STYLE)
               for col, _ in METRIC_COLUMNS]
        )
    table = Table(rows, colWidths=[UW * 0.16] + [UW * 0.105] * 8, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)
    return story


def generate_sector_report(sector: str, df: pd.DataFrame, path: Path) -> int:
    """Build one sector PDF and return the rendered page count."""
    margin = (21 * cm - UW) / 2
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"{sector} sector report",
    )
    doc.build(build_story(sector, df))
    return doc.page


def main() -> int:
    """Generate one PDF per broad sector into reports/sector/."""
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        df = fetch_sector_frame(conn)
    for sector, group in df.groupby("broad_sector", sort=True):
        slug = sector.replace(" ", "_").replace("/", "-")
        pages = generate_sector_report(sector, group, REPORT_DIR / f"{slug}_report.pdf")
        logger.info("%s companies=%d pages=%d", sector, len(group), pages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())