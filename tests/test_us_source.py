from datetime import UTC, date, datetime

from stockwatch.datasource import DailyBar, Quote
from stockwatch.datasource.us import USDataSource

TS = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)  # 美東 11:00


class FakeFinnhub:
    def get_quote(self, ticker: str) -> Quote:
        return Quote(ticker, TS, 189.42, 178.6, None)


class FakeYF:
    def __init__(self, bars=None, error: Exception | None = None) -> None:
        self.bars = bars or []
        self.error = error
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        self.calls.append((ticker, start, end))
        if self.error:
            raise self.error
        return self.bars


def test_quote_gets_volume_from_yfinance_for_market_date():
    yf = FakeYF([DailyBar("NVDA", date(2026, 10, 16), 1, 1, 1, 1, 123_456)])
    q = USDataSource(FakeFinnhub(), yf).get_quote("NVDA")  # type: ignore[arg-type]
    assert q.price == 189.42
    assert q.day_volume == 123_456
    assert yf.calls == [("NVDA", date(2026, 10, 16), date(2026, 10, 16))]


def test_volume_none_when_yfinance_fails_or_stale():
    for yf in (
        FakeYF(error=ConnectionError("down")),
        FakeYF([DailyBar("NVDA", date(2026, 10, 15), 1, 1, 1, 1, 9)]),
        FakeYF([]),
    ):
        q = USDataSource(FakeFinnhub(), yf).get_quote("NVDA")  # type: ignore[arg-type]
        assert q.day_volume is None
        assert q.price == 189.42
