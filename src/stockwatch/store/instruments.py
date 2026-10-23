"""instruments 表存取。"""

import sqlite3
from collections.abc import Iterable
from datetime import datetime

from stockwatch.config import Instrument


def sync_watchlist(
    conn: sqlite3.Connection, instruments: Iterable[Instrument], *, now: datetime
) -> None:
    """把 watchlist 同步進 instruments：新增的插入、既有的更新 market、
    不在清單上的 in_watchlist 設 0。重跑不重複。"""
    items = list(instruments)
    added_at = now.isoformat()
    with conn:
        conn.executemany(
            """
            INSERT INTO instruments (ticker, name, market, in_watchlist, added_at)
            VALUES (?, NULL, ?, 1, ?)
            ON CONFLICT (ticker) DO UPDATE SET
                market = excluded.market,
                in_watchlist = 1
            """,
            [(i.ticker, i.market, added_at) for i in items],
        )
        if items:
            placeholders = ",".join("?" for _ in items)
            conn.execute(
                f"UPDATE instruments SET in_watchlist = 0 WHERE ticker NOT IN ({placeholders})",
                [i.ticker for i in items],
            )
        else:
            conn.execute("UPDATE instruments SET in_watchlist = 0")


def list_watchlist(conn: sqlite3.Connection) -> list[Instrument]:
    rows = conn.execute(
        "SELECT ticker, market FROM instruments WHERE in_watchlist = 1 ORDER BY ticker"
    ).fetchall()
    return [Instrument(ticker=r["ticker"], market=r["market"]) for r in rows]
