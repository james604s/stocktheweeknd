"""Finnhub 實作：盤中價格（免費 tier 的 /quote 不含成交量）。新聞於階段 4 加入。

金鑰以 X-Finnhub-Token header 傳送，不放在 URL；錯誤訊息一律遮蔽金鑰。
"""

import logging
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Any

import httpx

from stockwatch.datasource import DailyBar, NewsItem, Quote
from stockwatch.redact import quiet_http_loggers, redact
from stockwatch.retry import retry

log = logging.getLogger(__name__)
quiet_http_loggers()

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubError(RuntimeError):
    """不可重試的錯誤：金鑰無效、代號錯誤、沒有資料。"""


class FinnhubRetryableError(FinnhubError):
    """暫時性錯誤：連線失敗、逾時、429、5xx。"""


def quote_from_json(ticker: str, data: Mapping[str, Any]) -> Quote:
    """解析 /quote 回應：c 現價、pc 前收、t 最後成交時間（epoch 秒）。

    代號錯誤時 Finnhub 回 200 但各欄位為 0，這裡視為錯誤。
    """
    price = data.get("c") or 0
    prev_close = data.get("pc") or 0
    ts = data.get("t") or 0
    if not price or not prev_close or not ts:
        raise FinnhubError(f"Finnhub 沒有 {ticker} 的報價（代號錯誤或無資料）")
    return Quote(
        ticker=ticker,
        ts=datetime.fromtimestamp(int(ts), tz=UTC),
        price=float(price),
        prev_close=float(prev_close),
        day_volume=None,
    )


class FinnhubSource:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("缺少 FINNHUB_KEY")
        self._key = api_key
        self._timeout = timeout
        self._transport = transport
        self._sleep = sleep

    def _get(self, path: str, params: dict[str, str]) -> Any:
        def call() -> Any:
            try:
                with httpx.Client(
                    base_url=BASE_URL,
                    timeout=self._timeout,
                    transport=self._transport,
                    headers={"X-Finnhub-Token": self._key},
                ) as client:
                    resp = client.get(path, params=params)
            except httpx.HTTPError as exc:
                detail = redact(str(exc), self._key)
                raise FinnhubRetryableError(
                    f"Finnhub {path} 連線失敗：{type(exc).__name__}: {detail}"
                ) from None
            if resp.status_code == 429 or resp.status_code >= 500:
                raise FinnhubRetryableError(f"Finnhub {path} 回應 {resp.status_code}")
            if resp.status_code >= 400:
                raise FinnhubError(f"Finnhub {path} 回應 {resp.status_code}")
            try:
                return resp.json()
            except ValueError:
                raise FinnhubError(f"Finnhub {path} 回應不是 JSON") from None

        return retry(
            call,
            attempts=3,
            exceptions=(FinnhubRetryableError,),
            sleep=self._sleep,
            what=f"Finnhub {path} {params.get('symbol', '')}",
        )

    def get_quote(self, ticker: str) -> Quote:
        return quote_from_json(ticker, self._get("/quote", {"symbol": ticker}))

    def get_daily_bars(self, ticker: str, start: date, end: date) -> list[DailyBar]:
        raise NotImplementedError("日線由 yfinance 提供")

    def get_news(self, ticker: str, since: datetime) -> list[NewsItem]:
        raise NotImplementedError("新聞於階段 4 實作")
