"""美股資料源：日線與盤中成交量用 yfinance，盤中價格用 Finnhub。

Finnhub 免費 tier 的 /quote 不含成交量，所以 get_quote 先拿 Finnhub 價格，
再用 yfinance 當日的日線補上累積成交量。成交量取不到時為 None，不影響價格規則。
"""

import logging
from dataclasses import replace
from datetime import date, datetime

from stockwatch import calendar as mcal
from stockwatch.datasource import DailyBar, NewsItem, Quote
from stockwatch.datasource.finnhub_source import FinnhubSource
from stockwatch.datasource.yfinance_source import YFinanceSource

log = logging.getLogger(__name__)


class USDataSource:
    market = "US"

    def __init__(self, finnhub: FinnhubSource, yfinance: YFinanceSource) -> None:
        self._finnhub = finnhub
        self._yfinance = yfinance

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        return self._yfinance.get_daily_bars(ticker, start, end)

    def get_quote(self, ticker: str) -> Quote:
        quote = self._finnhub.get_quote(ticker)
        return replace(quote, day_volume=self._day_volume(ticker, quote.ts))

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]:
        return self._finnhub.get_news(ticker, since)

    def _day_volume(self, ticker: str, ts: datetime) -> int | None:
        day = mcal.market_date(self.market, ts)
        try:
            bars = self._yfinance.get_daily_bars(ticker, day, day)
        except Exception as exc:
            log.warning("%s 當日成交量取得失敗：%s", ticker, exc)
            return None
        if not bars or bars[-1].date != day:
            log.warning("%s yfinance 沒有 %s 的日線，成交量暫缺", ticker, day)
            return None
        return bars[-1].volume
