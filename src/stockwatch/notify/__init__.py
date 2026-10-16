"""通知介面：notify(channel, payload)。

所有對外通知只能經過這個介面；Discord webhook 是其中一個 sender（階段 2 實作）。
外部呼叫必須有 timeout 與指數退避 retry（3 次）。
"""

from typing import Any, Literal

Channel = Literal["daily", "alerts", "holdings", "ops"]


def notify(channel: Channel, payload: dict[str, Any]) -> None:
    raise NotImplementedError("階段 2 實作 Discord sender")
