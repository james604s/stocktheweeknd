"""規則引擎。

規則是純函數：rule(ticker, quote, history) -> Optional[AlertPayload]。
不碰 DB、不讀系統時間、不發通知，只依賴傳入參數，可直接以 daily_bars 回測。
history 是報價日「之前」的日線，依日期遞增排序。
"""

from collections.abc import Callable
from dataclasses import dataclass

from stockwatch.datasource import DailyBar, Quote


@dataclass(frozen=True, slots=True)
class AlertPayload:
    ticker: str
    rule_id: str
    title: str  # 例：NVDA ▲ +6.2%
    fields: dict[str, str]  # 現價、前收、成交量倍數、觸發規則
    channels: tuple[str, ...]
    color: int  # 漲綠跌紅

    @property
    def key(self) -> tuple[str, str]:
        return (self.ticker, self.rule_id)


Rule = Callable[[str, Quote, list[DailyBar]], AlertPayload | None]
