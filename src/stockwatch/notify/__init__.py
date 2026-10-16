"""通知介面：notify(channel, payload)。

所有對外通知只能經過這個介面；Discord webhook 是其中一個 sender。
job 啟動時以 configure(sender) 註冊實作。
"""

from typing import Any, Literal, Protocol

Channel = Literal["daily", "alerts", "holdings", "ops"]


class Sender(Protocol):
    def send(self, channel: Channel, payload: dict[str, Any]) -> None: ...


_sender: Sender | None = None


def configure(sender: Sender | None) -> None:
    global _sender
    _sender = sender


def notify(channel: Channel, payload: dict[str, Any]) -> None:
    if _sender is None:
        raise RuntimeError("notify 尚未設定 sender，請先呼叫 configure()")
    _sender.send(channel, payload)
