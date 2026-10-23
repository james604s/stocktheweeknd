"""由日線算出日報用的純數字統計。純函數，可直接 pytest。"""

from dataclasses import dataclass
from datetime import date

from stockwatch.datasource import DailyBar

VOL_WINDOW = 20


@dataclass(frozen=True, slots=True)
class TickerStat:
    ticker: str
    date: date
    close: float
    prev_close: float | None
    pct_change: float | None  # 0.05 = +5%
    volume: int
    vol_avg20: float | None  # 前 20 個交易日均量（不含當日）
    vol_multiple: float | None  # 當日量 / vol_avg20


def compute_stat(ticker: str, bars: list[DailyBar], report_date: date) -> TickerStat | None:
    """bars 須依日期遞增。最後一筆不是 report_date 時視為無資料，回傳 None。"""
    if not bars or bars[-1].date != report_date:
        return None
    today = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else None
    prev_close = prev.close if prev else None
    pct = (today.close / prev_close - 1.0) if prev_close else None

    window = bars[-(VOL_WINDOW + 1) : -1]
    vol_avg = sum(b.volume for b in window) / VOL_WINDOW if len(window) == VOL_WINDOW else None
    multiple = (today.volume / vol_avg) if vol_avg else None

    return TickerStat(
        ticker=ticker,
        date=today.date,
        close=today.close,
        prev_close=prev_close,
        pct_change=pct,
        volume=today.volume,
        vol_avg20=vol_avg,
        vol_multiple=multiple,
    )
