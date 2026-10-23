from datetime import UTC, date, datetime

from stockwatch.config import Instrument
from stockwatch.datasource import DailyBar, Quote
from stockwatch.rules import AlertPayload
from stockwatch.store import connect, init_schema
from stockwatch.store.alerts import record_alerts, sent_keys
from stockwatch.store.bars import latest_bar_date, recent_bars, upsert_daily_bars
from stockwatch.store.instruments import list_watchlist, sync_watchlist
from stockwatch.store.quotes import upsert_quote

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


def test_upsert_quote_is_idempotent_and_allows_null_volume():
    conn = _conn()
    q = Quote("NVDA", NOW, 189.4, 178.6, None)
    upsert_quote(conn, q)
    upsert_quote(conn, Quote("NVDA", NOW, 189.5, 178.6, 1_000))
    rows = conn.execute("SELECT price, day_volume FROM quotes").fetchall()
    assert [(r["price"], r["day_volume"]) for r in rows] == [(189.5, 1_000)]


def test_alerts_sent_keeps_first_record():
    conn = _conn()
    p = AlertPayload("NVDA", "pct_move_5", "NVDA ▲ +6.2%", {"現價": "1"}, ("alerts",), 1)
    day = date(2026, 10, 16)
    record_alerts(conn, [p], day=day, ts=NOW)
    record_alerts(conn, [p], day=day, ts=datetime(2026, 10, 16, 23, tzinfo=UTC))
    rows = conn.execute("SELECT ts, payload FROM alerts_sent").fetchall()
    assert len(rows) == 1
    assert rows[0]["ts"] == NOW.isoformat()
    assert "NVDA ▲ +6.2%" in rows[0]["payload"]
    assert sent_keys(conn, day) == {("NVDA", "pct_move_5")}
    assert sent_keys(conn, date(2026, 10, 17)) == set()


def test_migrates_old_quotes_table_with_not_null_volume():
    conn = connect(":memory:")
    conn.executescript(
        "CREATE TABLE quotes (ticker TEXT NOT NULL, ts TEXT NOT NULL, price REAL NOT NULL,"
        " prev_close REAL NOT NULL, day_volume INTEGER NOT NULL, PRIMARY KEY (ticker, ts));"
        "INSERT INTO quotes VALUES ('NVDA', '2026-10-16T15:00:00+00:00', 1, 1, 5);"
    )
    init_schema(conn)
    init_schema(conn)  # 再跑一次不出錯
    cols = {c["name"]: c["notnull"] for c in conn.execute("PRAGMA table_info(quotes)")}
    assert cols["day_volume"] == 0
    assert conn.execute("SELECT day_volume FROM quotes").fetchone()[0] == 5

    fresh = _conn()
    fresh_cols = [tuple(c) for c in fresh.execute("PRAGMA table_info(quotes)")]
    migrated_cols = [tuple(c) for c in conn.execute("PRAGMA table_info(quotes)")]
    assert migrated_cols == fresh_cols  # 遷移後的結構與 schema.sql 一致
