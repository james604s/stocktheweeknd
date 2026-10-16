"""外部資料存取介面。

業務邏輯只能透過 DataSource 取資料，不得直接 import yfinance 或打 Finnhub。
實作（yfinance、finnhub）於階段 2 與 3 加入，測試一律用 tests/fixtures/ 的錄製回應。
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DailyBar:
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class Quote:
    ticker: str
    ts: datetime  # UTC aware
    price: float
    prev_close: float
    day_volume: int


@dataclass(frozen=True, slots=True)
class NewsItem:
    id: str
    ticker: str
    published_at: datetime  # UTC aware
    headline: str
    source: str
    url: str


class DataSource(Protocol):
    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]: ...

    def get_quote(self, ticker: str) -> Quote: ...

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]: ...
