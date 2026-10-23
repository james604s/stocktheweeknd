"""quotes 表存取。ts 以 UTC ISO 8601 文字存。"""

import sqlite3

from stockwatch.datasource import Quote


def upsert_quote(conn: sqlite3.Connection, quote: Quote) -> None:
    """同 (ticker, ts) 重寫不重複；盤後報價時間不變時即為同一列。"""
    with conn:
        conn.execute(
            """
            INSERT INTO quotes (ticker, ts, price, prev_close, day_volume)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (ticker, ts) DO UPDATE SET
                price = excluded.price,
                prev_close = excluded.prev_close,
                day_volume = excluded.day_volume
            """,
            (quote.ticker, quote.ts.isoformat(), quote.price, quote.prev_close, quote.day_volume),
        )
