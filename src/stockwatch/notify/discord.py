"""Discord webhook sender。timeout + 指數退避 retry（3 次）。"""

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from stockwatch.notify import Channel
from stockwatch.retry import retry

log = logging.getLogger(__name__)


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
            raise ValueError(
                f"頻道 {channel} 沒有設定 webhook（DISCORD_WEBHOOK_{channel.upper()}）"
            )

        def post() -> None:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()

        retry(post, attempts=3, sleep=self._sleep, what=f"Discord #{channel}")
        log.info("已推送 #%s", channel)
