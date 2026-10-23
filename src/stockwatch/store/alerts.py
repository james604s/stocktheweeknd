"""alerts_sent 表存取：同 ticker 同規則同一天只推一次。"""

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import asdict
from datetime import date, datetime

from stockwatch.rules import AlertPayload


def sent_keys(conn: sqlite3.Connection, day: date) -> set[tuple[str, str]]:
    rows = conn.execute(
        "SELECT ticker, rule_id FROM alerts_sent WHERE date = ?", (day.isoformat(),)
    ).fetchall()
    return {(r["ticker"], r["rule_id"]) for r in rows}


def record_alerts(
    conn: sqlite3.Connection, payloads: Iterable[AlertPayload], *, day: date, ts: datetime
) -> None:
    """已存在的 (ticker, rule_id, date) 保留第一次的紀錄。"""
    rows = [
        (
            p.ticker,
            p.rule_id,
            day.isoformat(),
            ts.isoformat(),
            json.dumps(asdict(p), ensure_ascii=False),
        )
        for p in payloads
    ]
    with conn:
        conn.executemany(
            """
            INSERT INTO alerts_sent (ticker, rule_id, date, ts, payload)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (ticker, rule_id, date) DO NOTHING
            """,
            rows,
        )
