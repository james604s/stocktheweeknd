"""yfinance 實作：只提供日線。盤中報價與新聞由 Finnhub 實作（階段 3、4）。"""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from stockwatch.datasource import DailyBar, NewsItem, Quote
from stockwatch.retry import retry

log = logging.getLogger(__name__)

_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

FetchFn = Callable[[str, date, date], pd.DataFrame]


def bars_from_frame(ticker: str, frame: pd.DataFrame) -> list[DailyBar]:
    """把 yfinance history() 回傳的 DataFrame 轉成 DailyBar；缺值列略過。"""
    bars: list[DailyBar] = []
    if frame.empty:
        return bars
    for ts, row in frame.iterrows():
        values = [row[c] for c in _COLUMNS]
        if any(pd.isna(v) for v in values):
            continue
        o, h, lo, c, v = values
        bars.append(
            DailyBar(
                ticker=ticker,
                date=pd.Timestamp(ts).date(),
                open=float(o),
                high=float(h),
                low=float(lo),
                close=float(c),
                volume=int(v),
            )
        )
    return bars


def _fetch_history(ticker: str, start: date, end: date, timeout: float) -> pd.DataFrame:
    # yfinance 的 end 為 exclusive，介面的 end 為 inclusive。
    return yf.Ticker(ticker).history(
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        timeout=timeout,
        raise_errors=True,
    )


class YFinanceSource:
    def __init__(
        self,
        *,
        timeout: float = 15.0,
        fetch: FetchFn | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._timeout = timeout
        self._fetch = fetch or (lambda t, s, e: _fetch_history(t, s, e, self._timeout))
        self._sleep = sleep

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        frame = retry(
            lambda: self._fetch(ticker, start, end),
            attempts=3,
            sleep=self._sleep,
            what=f"yfinance 日線 {ticker}",
        )
        bars = bars_from_frame(ticker, frame)
        log.info("yfinance %s %s~%s 取得 %d 筆", ticker, start, end, len(bars))
        return bars

    def get_quote(self, ticker: str) -> Quote:
        raise NotImplementedError("盤中報價由 Finnhub 實作（階段 3）")

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]:
        raise NotImplementedError("新聞由 Finnhub 實作（階段 4）")
