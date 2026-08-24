import sqlite3

import pandas as pd
import pytest

from src.etl.loader import init_db, write_frames

TABLES = {
    "companies",
    "profitandloss",
    "balancesheet",
    "cashflow",
    "analysis",
    "documents",
    "prosandcons",
    "sectors",
    "market_cap",
    "stock_prices",
}


def test_schema_creates_all_tables(tmp_path) -> None:
    conn = init_db(tmp_path / "test.db")
    names = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert TABLES <= names


def test_foreign_keys_enforced(tmp_path) -> None:
    conn = init_db(tmp_path / "test.db")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO profitandloss (company_id, year) VALUES ('ZZZZ', '2023-03')"
        )
    conn.close()


def test_write_frames_idempotent(tmp_path) -> None:
    conn = init_db(tmp_path / "test.db")
    frames = {
        "companies": pd.DataFrame(
            {"id": ["TCS"], "company_name": ["Tata Consultancy Services"]}
        ),
        "profitandloss": pd.DataFrame(
            {"company_id": ["TCS"], "year": ["2023-03"], "sales": [100.0]}
        ),
    }
    write_frames(conn, frames)
    write_frames(conn, frames)
    assert conn.execute("SELECT COUNT(*) FROM profitandloss").fetchone()[0] == 1
    conn.close()
