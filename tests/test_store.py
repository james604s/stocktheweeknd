from datetime import UTC, date, datetime

from stockwatch.config import Instrument
from stockwatch.datasource import DailyBar
from stockwatch.store import connect, init_schema
from stockwatch.store.bars import latest_bar_date, recent_bars, upsert_daily_bars
from stockwatch.store.instruments import list_watchlist, sync_watchlist

NOW = datetime(2026, 10, 16, 22, tzinfo=UTC)


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_upsert_daily_bars_is_idempotent():
    conn = _conn()
    bar = DailyBar("NVDA", date(2026, 10, 16), 1, 2, 0.5, 1.5, 100)
    upsert_daily_bars(conn, [bar])
    upsert_daily_bars(conn, [bar, DailyBar("NVDA", date(2026, 10, 16), 1, 2, 0.5, 1.7, 200)])
    rows = conn.execute("SELECT close, volume FROM daily_bars").fetchall()
    assert len(rows) == 1
    assert (rows[0]["close"], rows[0]["volume"]) == (1.7, 200)


def test_latest_and_recent_bars():
    conn = _conn()
    assert latest_bar_date(conn, "NVDA") is None
    bars = [DailyBar("NVDA", date(2026, 10, d), 1, 2, 0.5, float(d), 10) for d in (13, 14, 15, 16)]
    upsert_daily_bars(conn, bars)
    upsert_daily_bars(conn, [DailyBar("AAPL", date(2026, 10, 16), 1, 2, 0.5, 9, 10)])
    assert latest_bar_date(conn, "NVDA") == date(2026, 10, 16)
    recent = recent_bars(conn, "NVDA", end=date(2026, 10, 15), limit=2)
    assert [b.date.day for b in recent] == [14, 15]
    assert all(b.ticker == "NVDA" for b in recent)


def test_sync_watchlist_marks_removed():
    conn = _conn()
    sync_watchlist(conn, [Instrument("NVDA", "US"), Instrument("AAPL", "US")], now=NOW)
    sync_watchlist(conn, [Instrument("NVDA", "US")], now=NOW)
    assert list_watchlist(conn) == [Instrument("NVDA", "US")]
    assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 2
    # 重新加回：不重複、in_watchlist 回到 1
    sync_watchlist(conn, [Instrument("NVDA", "US"), Instrument("AAPL", "US")], now=NOW)
    assert [i.ticker for i in list_watchlist(conn)] == ["AAPL", "NVDA"]
    assert conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == 2
