"""規則引擎。

規則是純函數：rule(ticker, quote, history) -> Optional[AlertPayload]。
不碰 DB、不讀系統時間、不發通知，只依賴傳入參數，可直接以 daily_bars 回測。
規則載入（rules.yaml）與 dedupe 於階段 3 實作；必須有 pytest。
"""

from collections.abc import Callable
from dataclasses import dataclass

from stockwatch.datasource import DailyBar, Quote


@dataclass(frozen=True, slots=True)
class AlertPayload:
    ticker: str
    rule_id: str
    title: str
    fields: dict[str, str]
    channels: tuple[str, ...]


Rule = Callable[[str, Quote, list[DailyBar]], AlertPayload | None]
