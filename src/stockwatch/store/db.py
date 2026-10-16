"""SQLite 連線與 schema 初始化。"""

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_RESOURCE = "schema.sql"


def connect(path: str | Path) -> sqlite3.Connection:
    """開啟資料庫連線。path 為 ":memory:" 時用於測試。"""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """建立所有資料表；全部為 CREATE TABLE IF NOT EXISTS，可重複執行。"""
    sql = resources.files("stockwatch.store").joinpath(SCHEMA_RESOURCE).read_text("utf-8")
    with conn:
        conn.executescript(sql)
