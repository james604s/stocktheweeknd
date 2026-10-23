"""schema 建立與重複執行（idempotent）測試。"""

import sqlite3

from stockwatch.store import connect, init_schema

EXPECTED_TABLES = {
    "instruments",
    "daily_bars",
    "quotes",
    "indicators",
    "news",
    "transactions",
    "alerts_sent",
    "daily_summaries",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def test_init_schema_creates_all_tables() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    assert _tables(conn) == EXPECTED_TABLES


def test_init_schema_is_idempotent() -> None:
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute(
        "INSERT INTO instruments (ticker, market, added_at) VALUES (?, ?, ?)",
        ("NVDA", "US", "2026-10-16T00:00:00+00:00"),
    )
    init_schema(conn)
    assert _tables(conn) == EXPECTED_TABLES
    assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 1
