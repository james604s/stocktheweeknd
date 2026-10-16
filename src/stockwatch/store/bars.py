"""daily_bars 表存取。date 以 ISO 8601 文字存。"""

import sqlite3
from collections.abc import Iterable
from datetime import date

from stockwatch.datasource import DailyBar


def upsert_daily_bars(conn: sqlite3.Connection, bars: Iterable[DailyBar]) -> int:
    """upsert；同 (ticker, date) 重跑不產生重複列。回傳處理筆數。"""
    rows = [(b.ticker, b.date.isoformat(), b.open, b.high, b.low, b.close, b.volume) for b in bars]
    with conn:
        conn.executemany(
            """
            INSERT INTO daily_bars (ticker, date, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, date) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume
            """,
            rows,
        )
    return len(rows)


def latest_bar_date(conn: sqlite3.Connection, ticker: str) -> date | None:
    row = conn.execute(
        "SELECT MAX(date) AS d FROM daily_bars WHERE ticker = ?", (ticker,)
    ).fetchone()
    return date.fromisoformat(row["d"]) if row and row["d"] else None


def recent_bars(conn: sqlite3.Connection, ticker: str, *, end: date, limit: int) -> list[DailyBar]:
    """end（含）之前最近 limit 筆日線，依日期遞增排序。"""
    rows = conn.execute(
        """
        SELECT ticker, date, open, high, low, close, volume
        FROM daily_bars
        WHERE ticker = ? AND date <= ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (ticker, end.isoformat(), limit),
    ).fetchall()
    bars = [
        DailyBar(
            ticker=r["ticker"],
            date=date.fromisoformat(r["date"]),
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
        )
        for r in rows
    ]
    bars.reverse()
    return bars
