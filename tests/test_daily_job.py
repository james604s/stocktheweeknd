"""jobs/daily.py 整合測試：假資料源 + 假 sender + 暫存 DB，不打任何 API。"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import daily
from stockwatch.config import Settings
from stockwatch.datasource import DailyBar, NewsItem, Quote
from stockwatch.notify import configure

FRIDAY_CLOSE = datetime(2026, 10, 16, 22, 0, tzinfo=UTC)
REPORT_DATE = date(2026, 10, 16)


class FakeSource:
    def __init__(self, *, fail: set[str] = frozenset()) -> None:
        self.calls: list[tuple[str, date, date]] = []
        self.fail = fail

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        self.calls.append((ticker, start, end))
        if ticker in self.fail:
            raise ConnectionError("down")
        bars = []
        d = start
        i = 0
        while d <= end:
            if d.weekday() < 5:
                close = 100.0 + i
                bars.append(DailyBar(ticker, d, close, close + 1, close - 1, close, 1_000 + i))
                i += 1
            d += timedelta(days=1)
        return bars

    def get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]:
        raise NotImplementedError


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, channel: str, payload: dict[str, Any]) -> None:
        self.sent.append((channel, payload))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    wl = tmp_path / "watchlist.yaml"
    wl.write_text("instruments:\n  - {ticker: NVDA, market: US}\n  - {ticker: AAPL, market: US}\n")
    return Settings(db_path=tmp_path / "data" / "stock.db", watchlist_path=wl)


@pytest.fixture
def sender() -> FakeSender:
    s = FakeSender()
    configure(s)
    yield s
    configure(None)


def test_run_sends_daily_report(settings, sender):
    source = FakeSource()
    assert daily.run(settings, now=FRIDAY_CLOSE, source=source) is True

    # 首次抓取回看 60 天
    assert source.calls[0] == ("NVDA", REPORT_DATE - timedelta(days=60), REPORT_DATE)
    assert [c for c, _ in sender.sent] == ["daily"]
    embed = sender.sent[0][1]["embeds"][0]
    assert embed["title"] == "stockwatch 日報 2026-10-16（美股）"
    value = embed["fields"][0]["value"]
    assert "**NVDA**" in value and "**AAPL**" in value
    assert "量 " in value and "n/a" not in value  # 60 天資料足夠算 20 日均量


def test_run_is_idempotent_and_incremental(settings, sender):
    source = FakeSource()
    daily.run(settings, now=FRIDAY_CLOSE, source=source)
    daily.run(settings, now=FRIDAY_CLOSE, source=source)

    from stockwatch.store import connect

    conn = connect(settings.db_path)
    rows = conn.execute(
        "SELECT ticker, COUNT(*) AS n FROM daily_bars GROUP BY ticker ORDER BY ticker"
    ).fetchall()
    # 每檔 45 個平日（起訖含 61 天），兩次執行不重複
    assert [(r["ticker"], r["n"]) for r in rows] == [("AAPL", 45), ("NVDA", 45)]
    # 第二次只回補 5 天
    assert source.calls[2] == ("NVDA", REPORT_DATE - timedelta(days=5), REPORT_DATE)
    assert len(sender.sent) == 2


def test_run_skips_non_trading_day(settings, sender):
    source = FakeSource()
    saturday = datetime(2026, 10, 17, 22, tzinfo=UTC)
    assert daily.run(settings, now=saturday, source=source) is False
    assert source.calls == []
    assert sender.sent == []


def test_run_reports_fetch_failures_to_ops_but_still_sends(settings, sender):
    source = FakeSource(fail={"AAPL"})
    assert daily.run(settings, now=FRIDAY_CLOSE, source=source) is True
    channels = [c for c, _ in sender.sent]
    assert channels == ["daily", "ops"]
    embed = sender.sent[0][1]["embeds"][0]
    names = [f["name"] for f in embed["fields"]]
    assert "當日無資料" in names
    assert "AAPL" in sender.sent[1][1]["content"]


def test_failure_summary_fits_discord_limit(settings, sender):
    tickers = [f"T{i:02d}" for i in range(40)]
    settings.watchlist_path.write_text(
        "instruments:\n" + "".join(f"  - {{ticker: {t}, market: US}}\n" for t in tickers)
    )
    source = FakeSource(fail=set(tickers))
    daily.run(settings, now=FRIDAY_CLOSE, source=source)
    ops = [p["content"] for c, p in sender.sent if c == "ops"]
    assert len(ops) == 1
    assert len(ops[0]) <= 2000
    assert "有 40 檔抓取失敗" in ops[0]
    assert "另有 30 檔" in ops[0]


def test_format_failures_truncates_long_errors():
    msg = daily.format_failures(REPORT_DATE, {"NVDA": "x" * 500})
    line = msg.splitlines()[1]
    assert len(line) <= len("- NVDA: ") + daily.MAX_ERROR_CHARS


def test_main_reports_to_ops_and_reraises(monkeypatch, settings):
    fake = FakeSender()
    monkeypatch.setattr(daily, "load_settings", lambda: settings)
    monkeypatch.setattr(daily, "DiscordSender", lambda webhooks: fake)

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(daily, "run", boom)
    with pytest.raises(RuntimeError, match="kaboom"):
        daily.main()
    assert [c for c, _ in fake.sent] == ["ops"]
    assert "kaboom" in fake.sent[0][1]["content"]
    configure(None)


def test_main_reraises_when_settings_fail(monkeypatch):
    def bad_settings():
        raise ValueError("bad .env")

    monkeypatch.setattr(daily, "load_settings", bad_settings)
    configure(None)
    with pytest.raises(ValueError, match="bad .env"):
        daily.main()
