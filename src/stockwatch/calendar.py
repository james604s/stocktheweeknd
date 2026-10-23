"""交易日曆與時段判斷，依 instruments.market 查表。

這是全專案唯一允許知道「哪個市場何時開盤」的地方；
其他模組不得寫死 NYSE 或美東時間。v1 只有 US，階段 3.5 加 TW。
"""

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

Market = Literal["US"]

# market -> (exchange_calendars 代碼, 當地時區)
_MARKETS: dict[str, tuple[str, str]] = {
    "US": ("XNYS", "America/New_York"),
}

# market -> 哨兵在收盤後繼續檢查的緩衝時間
_WATCH_BUFFER: dict[str, timedelta] = {
    "US": timedelta(minutes=30),
}


def _spec(market: str) -> tuple[str, str]:
    try:
        return _MARKETS[market]
    except KeyError as exc:
        raise ValueError(f"未知市場：{market}") from exc


@lru_cache
def _calendar(market: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(_spec(market)[0])


def market_tz(market: str) -> ZoneInfo:
    return ZoneInfo(_spec(market)[1])


def market_date(market: str, now: datetime) -> date:
    """UTC aware 的 now 在該市場當地的日期。"""
    if now.tzinfo is None:
        raise ValueError("now 必須是 aware datetime")
    return now.astimezone(market_tz(market)).date()


def is_trading_day(market: str, d: date) -> bool:
    return bool(_calendar(market).is_session(pd.Timestamp(d)))


def session_close(market: str, d: date) -> datetime:
    """該交易日收盤時間（UTC aware）。d 必須是交易日。"""
    return _calendar(market).session_close(pd.Timestamp(d)).to_pydatetime()


def session_open(market: str, d: date) -> datetime:
    """該交易日開盤時間（UTC aware）。d 必須是交易日。"""
    return _calendar(market).session_open(pd.Timestamp(d)).to_pydatetime()


def in_watch_window(market: str, now: datetime) -> bool:
    """now 是否在哨兵的檢查時段：交易日的開盤到收盤加緩衝。提早收盤日依實際收盤時間。"""
    d = market_date(market, now)
    if not is_trading_day(market, d):
        return False
    buffer = _WATCH_BUFFER.get(market, timedelta(0))
    return session_open(market, d) <= now <= session_close(market, d) + buffer


def previous_trading_day(market: str, d: date) -> date:
    """嚴格早於 d 的最近交易日。"""
    return _calendar(market).previous_session(pd.Timestamp(d)).date()


def completed_session(market: str, now: datetime) -> date | None:
    """若 now 在當地的日期是交易日且已收盤，回傳該日期；否則 None。

    日報 job 用它判斷「今天該不該發」：台灣 06:00 等於美東前一日傍晚，
    當地日期即剛收盤的那個交易日。
    """
    d = market_date(market, now)
    if not is_trading_day(market, d):
        return None
    if now < session_close(market, d):
        return None
    return d
