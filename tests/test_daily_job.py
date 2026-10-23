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
    """每個日期的價量固定。

    設定 split_ratio 模擬分割之後的 Yahoo：分割前的歷史回溯調整，分割後的實際交易
    本來就以新股數計，所以所有日期都是「價 / 比例、量 × 比例」。
    """

    def __init__(self, *, fail: set[str] = frozenset()) -> None:
        self.calls: list[tuple[str, date, date]] = []
        self.fail = fail
        self.split_ratio: float | None = None

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        self.calls.append((ticker, start, end))
        if ticker in self.fail:
            raise ConnectionError("down")
        bars = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                close = 100.0 + (d - date(2026, 1, 1)).days * 0.1
                volume = 1_000 + d.toordinal() % 7
                if self.split_ratio:
                    close /= self.split_ratio
                    volume = int(volume * self.split_ratio)
                bars.append(DailyBar(ticker, d, close, close + 1, close - 1, close, volume))
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
    # 第二次只回補 5 天，資料沒被改寫就不重抓
    assert source.calls[2] == ("NVDA", REPORT_DATE - timedelta(days=5), REPORT_DATE)
    assert len(source.calls) == 4
    assert len(sender.sent) == 2


def test_split_triggers_full_refetch(settings, sender):
    from stockwatch.store import connect

    source = FakeSource()
    earlier = datetime(2026, 10, 9, 22, tzinfo=UTC)  # 前一週五
    daily.run(settings, now=earlier, source=source)

    source.split_ratio = 10.0  # 這週發生 10:1 分割
    sender.sent.clear()
    source.calls.clear()
    daily.run(settings, now=FRIDAY_CLOSE, source=source)

    nvda = [c for c in source.calls if c[0] == "NVDA"]
    assert nvda[0][1] == date(2026, 10, 9) - timedelta(days=5)  # 回補
    assert nvda[1] == ("NVDA", date(2026, 10, 9) - timedelta(days=60), REPORT_DATE)  # 整段重抓

    conn = connect(settings.db_path)
    first = conn.execute(
        "SELECT close, volume FROM daily_bars WHERE ticker='NVDA' ORDER BY date LIMIT 1"
    ).fetchone()
    expected = source.get_daily_bars("NVDA", date(2026, 8, 10), date(2026, 8, 10))[0]
    assert first["close"] == pytest.approx(expected.close)
    assert first["volume"] == expected.volume

    value = sender.sent[0][1]["embeds"][0]["fields"][0]["value"]
    assert "量 1.0x" in value  # 未重抓的話會顯示接近 10x
    ops = [p["content"] for c, p in sender.sent if c == "ops"]
    assert len(ops) == 1 and "NVDA" in ops[0] and "AAPL" in ops[0]


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
