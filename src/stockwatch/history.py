"""日線同步：首次抓取、增量回補，偵測到歷史被改寫時整段重抓。

Yahoo 的價格與成交量會回溯調整股票分割。只回補最近幾天的話，
DB 裡較舊的日線仍是分割前的數字，均量倍數與均線會失真。
因此每次回補都拿重疊區間比對收盤價，差異超過門檻就整段重抓覆蓋。
"""

import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from stockwatch.datasource import DailyBar, DataSource
from stockwatch.store.bars import (
    bars_between,
    earliest_bar_date,
    latest_bar_date,
    upsert_daily_bars,
)

log = logging.getLogger(__name__)

INITIAL_DAYS = 60  # 首次抓取回看天數
BACKFILL_DAYS = 5  # 增量抓取回補天數，防缺漏，同時作為比對區間
REVISION_TOLERANCE = 0.01  # 收盤價差異超過 1% 視為歷史被改寫；分割比例至少 5:4


@dataclass(frozen=True, slots=True)
class SyncResult:
    ticker: str
    fetched: int
    refreshed_from: date | None = None  # 有整段重抓時為重抓起始日


def history_revised(
    stored: list[DailyBar], fetched: list[DailyBar], tolerance: float = REVISION_TOLERANCE
) -> bool:
    """純函數：同一天的收盤價，新抓的與 DB 的差異超過 tolerance 就回傳 True。"""
    by_date = {b.date: b for b in stored}
    for bar in fetched:
        old = by_date.get(bar.date)
        if old is not None and old.close > 0 and abs(bar.close / old.close - 1.0) > tolerance:
            return True
    return False


def sync_daily_bars(
    conn: sqlite3.Connection, source: DataSource, ticker: str, end: date
) -> SyncResult:
    latest = latest_bar_date(conn, ticker)
    if latest is None:
        bars = source.get_daily_bars(ticker, end - timedelta(days=INITIAL_DAYS), end)
        upsert_daily_bars(conn, bars)
        return SyncResult(ticker, len(bars))

    start = latest - timedelta(days=BACKFILL_DAYS)
    bars = source.get_daily_bars(ticker, start, end)
    stored = bars_between(conn, ticker, start, latest)
    refreshed_from: date | None = None
    if history_revised(stored, bars):
        refreshed_from = earliest_bar_date(conn, ticker) or start
        log.warning("%s 歷史價格被改寫（可能是股票分割），自 %s 起整段重抓", ticker, refreshed_from)
        bars = source.get_daily_bars(ticker, refreshed_from, end)
    upsert_daily_bars(conn, bars)
    return SyncResult(ticker, len(bars), refreshed_from)
