"""jobs/watch.py 整合測試：假資料源 + 假 sender + 暫存 DB，不打任何 API。"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import watch
from stockwatch.config import Settings
from stockwatch.datasource import DailyBar, NewsItem, Quote
from stockwatch.notify import configure
from stockwatch.rules.builtin import pct_change_vs_prev_close, volume_vs_avg20
from stockwatch.store import connect, init_schema
from stockwatch.store.bars import upsert_daily_bars

IN_SESSION = datetime(2026, 10, 16, 15, 10, tzinfo=UTC)  # 週五 美東 11:10
RULES = [
    pct_change_vs_prev_close(rule_id="pct_move_5", threshold=0.05, channels=("alerts",)),
    volume_vs_avg20(rule_id="vol_spike_2x", multiplier=2.0, channels=("alerts",)),
]


class FakeSource:
    def __init__(self, prices: dict[str, float], volumes: dict[str, int] | None = None) -> None:
        self.prices = prices
        self.volumes = volumes or {}
        self.calls: list[str] = []

    def get_quote(self, ticker: str) -> Quote:
        self.calls.append(ticker)
        if ticker not in self.prices:
            raise ConnectionError("no quote")
        return Quote(ticker, IN_SESSION, self.prices[ticker], 100.0, self.volumes.get(ticker))

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        raise NotImplementedError

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]:
        raise NotImplementedError


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, channel: str, payload: dict[str, Any]) -> None:
        self.sent.append((channel, payload))


def _settings(tmp_path: Path, tickers: list[str]) -> Settings:
    wl = tmp_path / "watchlist.yaml"
    wl.write_text("instruments:\n" + "".join(f"  - {{ticker: {t}, market: US}}\n" for t in tickers))
    db = tmp_path / "data" / "stock.db"
    db.parent.mkdir()
    conn = connect(db)
    init_schema(conn)
    bars = [
        DailyBar(t, date(2026, 9, 1) + timedelta(days=i), 100, 101, 99, 100, 1_000)
        for t in tickers
        for i in range(40)
        if (date(2026, 9, 1) + timedelta(days=i)).weekday() < 5
    ]
    upsert_daily_bars(conn, bars)
    conn.close()
    return Settings(db_path=db, watchlist_path=wl)


@pytest.fixture
def sender():
    s = FakeSender()
    configure(s)
    yield s
    configure(None)


def test_outside_window_makes_no_calls(tmp_path, sender):
    source = FakeSource({"NVDA": 110})
    saturday = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
    assert (
        watch.run(_settings(tmp_path, ["NVDA"]), now=saturday, source=source, rules=RULES) is None
    )
    assert source.calls == []
    assert sender.sent == []


def test_alerts_are_pushed_once_per_day(tmp_path, sender):
    settings = _settings(tmp_path, ["NVDA", "AAPL"])
    source = FakeSource({"NVDA": 106.2, "AAPL": 101.0}, {"NVDA": 1_000, "AAPL": 2_500})

    r1 = watch.run(settings, now=IN_SESSION, source=source, rules=RULES)
    assert r1 is not None and (r1.checked, r1.hits, r1.pushed) == (2, 2, 2)
    titles = [p["embeds"][0]["title"] for c, p in sender.sent if c == "alerts"]
    assert sorted(titles) == ["AAPL ▲ +1.0%", "NVDA ▲ +6.2%"]

    sender.sent.clear()
    r2 = watch.run(settings, now=IN_SESSION + timedelta(minutes=5), source=source, rules=RULES)
    assert r2 is not None and (r2.hits, r2.pushed) == (2, 0)  # 同日同規則不重推
    assert sender.sent == []

    conn = connect(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM alerts_sent").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0] == 2


def test_volume_history_excludes_today(tmp_path, sender):
    settings = _settings(tmp_path, ["NVDA"])
    conn = connect(settings.db_path)
    # 今天若已有一筆極大量的日線（例如手動補資料），不得混進 20 日均量
    upsert_daily_bars(conn, [DailyBar("NVDA", date(2026, 10, 16), 1, 1, 1, 1, 10**9)])
    conn.close()
    source = FakeSource({"NVDA": 100.0}, {"NVDA": 2_000})
    r = watch.run(settings, now=IN_SESSION, source=source, rules=RULES)
    assert r is not None and r.hits == 1


def test_flood_is_capped_at_ten_messages(tmp_path, sender):
    tickers = [f"T{i:02d}" for i in range(15)]
    settings = _settings(tmp_path, tickers)
    source = FakeSource({t: 110.0 for t in tickers})
    r = watch.run(settings, now=IN_SESSION, source=source, rules=RULES)
    assert r is not None and r.hits == 15 and r.pushed == 10
    assert len([c for c, _ in sender.sent if c == "alerts"]) == 10
    conn = connect(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM alerts_sent").fetchone()[0] == 15


def test_quote_failures_do_not_stop_round_and_heartbeat_reports_them(tmp_path, sender):
    settings = _settings(tmp_path, ["NVDA", "BAD"])
    source = FakeSource({"NVDA": 100.0})
    top_of_hour = datetime(2026, 10, 16, 16, 0, tzinfo=UTC)
    r = watch.run(settings, now=top_of_hour, source=source, rules=RULES)
    assert r is not None and r.failed == ["BAD"]
    ops = [p["content"] for c, p in sender.sent if c == "ops"]
    assert len(ops) == 1
    assert ops[0].startswith("💓 哨兵存活，本輪檢查 2 檔，命中 0 條")
    assert "報價失敗：BAD" in ops[0]


def test_no_heartbeat_off_the_hour(tmp_path, sender):
    settings = _settings(tmp_path, ["NVDA"])
    watch.run(settings, now=IN_SESSION, source=FakeSource({"NVDA": 100.0}), rules=RULES)
    assert [c for c, _ in sender.sent] == []


def test_main_outside_window_skips_data_sources(monkeypatch, tmp_path):
    fake = FakeSender()
    settings = Settings(
        db_path=tmp_path / "x.db",
        watchlist_path=tmp_path / "w.yaml",
        healthchecks_watch="https://hc.test/abc",
    )
    pings: list[bool] = []
    monkeypatch.setattr(watch, "load_settings", lambda: settings)
    monkeypatch.setattr(watch, "DiscordSender", lambda webhooks: fake)
    monkeypatch.setattr(watch, "ping", lambda url, fail=False: pings.append(fail))
    monkeypatch.setattr(watch.mcal, "in_watch_window", lambda market, now: False)

    def no_source(*args, **kwargs):
        raise AssertionError("時段外不應建立資料源")

    monkeypatch.setattr(watch, "FinnhubSource", no_source)
    assert watch.main() == 0
    assert pings == [False]  # 時段外仍 ping，證明 cron 還在跑
    assert fake.sent == []
    configure(None)


def test_main_reports_errors_to_ops(monkeypatch, tmp_path):
    fake = FakeSender()
    settings = Settings(rules_path=tmp_path / "missing.yaml")
    monkeypatch.setattr(watch, "load_settings", lambda: settings)
    monkeypatch.setattr(watch, "DiscordSender", lambda webhooks: fake)
    with pytest.raises(FileNotFoundError):
        watch.main()
    assert [c for c, _ in fake.sent] == ["ops"]
    configure(None)
