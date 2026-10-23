import json
import logging
import traceback

import httpx
import pytest

from stockwatch.notify.discord import (
    CONTENT_LIMIT,
    DiscordError,
    DiscordRetryableError,
    DiscordSender,
)

URL = "https://discord.com/api/webhooks/123/SECRET_TOKEN"


def _sender(handler, sleep, channel: str = "daily") -> DiscordSender:
    return DiscordSender({channel: URL}, transport=httpx.MockTransport(handler), sleep=sleep)


def test_send_posts_json_and_retries_on_5xx(no_sleep):
    sleep, delays = no_sleep
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500 if len(seen) == 1 else 204)

    _sender(handler, sleep).send("daily", {"content": "hi"})
    assert len(seen) == 2
    assert seen[0].url == URL
    assert seen[0].headers["content-type"] == "application/json"
    assert b'"content":"hi"' in seen[0].content.replace(b" ", b"")
    assert delays == [1.0]


def test_4xx_is_not_retried(no_sleep):
    sleep, delays = no_sleep
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"message": "Invalid Form Body"})

    with pytest.raises(DiscordError) as info:
        _sender(handler, sleep).send("daily", {"content": "x"})
    assert not isinstance(info.value, DiscordRetryableError)
    assert len(calls) == 1
    assert delays == []


def test_429_waits_retry_after_then_succeeds(no_sleep):
    sleep, delays = no_sleep
    responses = [httpx.Response(429, json={"retry_after": 2.5}), httpx.Response(204)]
    _sender(lambda req: responses.pop(0), sleep).send("daily", {"content": "x"})
    assert delays == [2.5, 1.0]  # 先等 Discord 指定秒數，再加 retry 退避


def test_429_wait_is_capped(no_sleep):
    sleep, delays = no_sleep
    responses = [httpx.Response(429, headers={"Retry-After": "999"}), httpx.Response(204)]
    _sender(lambda req: responses.pop(0), sleep).send("daily", {"content": "x"})
    assert delays[0] == 30.0


def test_errors_never_contain_webhook_token(no_sleep):
    sleep, _ = no_sleep

    def http_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text=f"unknown webhook {URL}")

    def conn_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {URL}", request=request)

    for handler in (http_error, conn_error):
        with pytest.raises(DiscordError) as info:
            _sender(handler, sleep, "ops").send("ops", {"content": "x"})
        tb = "".join(traceback.format_exception(info.value))
        assert "SECRET_TOKEN" not in tb
        assert info.value.__cause__ is None
        assert info.value.__suppress_context__ or info.value.__context__ is None


def test_long_content_is_truncated(no_sleep):
    sleep, _ = no_sleep
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    payload = {"content": "x" * 5000}
    _sender(handler, sleep).send("daily", payload)
    sent = json.loads(seen[0].content)["content"]
    assert len(sent) == CONTENT_LIMIT
    assert sent.endswith("…")
    assert len(payload["content"]) == 5000  # 不改動呼叫端的 payload


def test_send_without_webhook_configured():
    sender = DiscordSender({})
    with pytest.raises(ValueError, match="DISCORD_WEBHOOK_ALERTS"):
        sender.send("alerts", {})


def test_successful_send_does_not_log_token(no_sleep, caplog):
    sleep, _ = no_sleep
    with caplog.at_level(logging.INFO):
        _sender(lambda req: httpx.Response(204), sleep).send("daily", {"content": "x"})
    assert "已推送 #daily" in caplog.text
    assert "SECRET_TOKEN" not in caplog.text
