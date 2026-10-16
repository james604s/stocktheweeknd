"""Discord webhook sender。timeout + 指數退避 retry（3 次）。

webhook URL 內含金鑰，所有對外拋出的錯誤都不得帶 URL，也不串接原始 httpx 例外。
"""

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from stockwatch.notify import Channel
from stockwatch.redact import quiet_http_loggers, redact
from stockwatch.retry import retry

log = logging.getLogger(__name__)
quiet_http_loggers()

CONTENT_LIMIT = 2000  # Discord 訊息 content 上限
MAX_RATE_LIMIT_WAIT = 30.0


class DiscordError(RuntimeError):
    """推送失敗，不可重試（例如 400 payload 錯誤、401/404 webhook 失效）。"""


class DiscordRetryableError(DiscordError):
    """暫時性錯誤：連線失敗、逾時、429、5xx。"""


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _retry_after(resp: httpx.Response) -> float:
    seconds: float = 1.0
    try:
        seconds = float(resp.json()["retry_after"])
    except Exception:
        try:
            seconds = float(resp.headers.get("Retry-After", seconds))
        except ValueError:
            pass
    return max(0.0, min(seconds, MAX_RATE_LIMIT_WAIT))


class DiscordSender:
    def __init__(
        self,
        webhooks: Mapping[str, str],
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._webhooks = dict(webhooks)
        self._timeout = timeout
        self._transport = transport
        self._sleep = sleep

    def send(self, channel: Channel, payload: dict[str, Any]) -> None:
        url = self._webhooks.get(channel)
        if not url:
            env_name = f"DISCORD_WEBHOOK_{channel.upper()}"
            raise ValueError(f"頻道 {channel} 沒有設定 webhook（{env_name}）")

        body = dict(payload)
        if isinstance(body.get("content"), str):
            body["content"] = truncate(body["content"], CONTENT_LIMIT)

        def post() -> None:
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                    resp = client.post(url, json=body)
            except httpx.HTTPError as exc:
                detail = redact(str(exc), url)
                raise DiscordRetryableError(
                    f"Discord #{channel} 連線失敗：{type(exc).__name__}: {detail}"
                ) from None
            status = resp.status_code
            if status == 429:
                self._sleep(_retry_after(resp))
                raise DiscordRetryableError(f"Discord #{channel} 被限流（429）")
            if status >= 500:
                raise DiscordRetryableError(f"Discord #{channel} 回應 {status}")
            if status >= 400:
                detail = redact(resp.text[:200], url)
                raise DiscordError(f"Discord #{channel} 回應 {status}：{detail}")

        retry(
            post,
            attempts=3,
            exceptions=(DiscordRetryableError,),
            sleep=self._sleep,
            what=f"Discord #{channel}",
        )
        log.info("已推送 #%s", channel)
