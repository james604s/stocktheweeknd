"""SQLite 連線與 schema 初始化。"""

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_RESOURCE = "schema.sql"

# 階段 3 起 quotes.day_volume 可為 NULL。這段 DDL 必須與 schema.sql 的 quotes 一致，
# tests/test_store.py 會比對兩者。
_QUOTES_DDL = """
CREATE TABLE quotes (
    ticker      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    price       REAL NOT NULL,
    prev_close  REAL NOT NULL,
    day_volume  INTEGER,
    PRIMARY KEY (ticker, ts)
)
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """開啟資料庫連線。path 為 ":memory:" 時用於測試。"""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """建立所有資料表並套用遷移；可重複執行。"""
    sql = resources.files("stockwatch.store").joinpath(SCHEMA_RESOURCE).read_text("utf-8")
    with conn:
        conn.executescript(sql)
    _migrate_quotes_nullable_volume(conn)


def _migrate_quotes_nullable_volume(conn: sqlite3.Connection) -> None:
    """階段 1、2 建立的 DB 中 quotes.day_volume 為 NOT NULL，重建資料表以放寬，保留既有資料。"""
    cols = conn.execute("PRAGMA table_info(quotes)").fetchall()
    if not any(c["name"] == "day_volume" and c["notnull"] for c in cols):
        return
    conn.executescript(
        "BEGIN;"
        "ALTER TABLE quotes RENAME TO quotes_old;"
        f"{_QUOTES_DDL};"
        "INSERT INTO quotes SELECT ticker, ts, price, prev_close, day_volume FROM quotes_old;"
        "DROP TABLE quotes_old;"
        "COMMIT;"
    )
