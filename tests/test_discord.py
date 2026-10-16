import httpx
import pytest

from stockwatch.notify.discord import DiscordSender

URL = "https://discord.test/webhook/daily"


def test_send_posts_json_and_retries_on_5xx(no_sleep):
    sleep, delays = no_sleep
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500 if len(seen) == 1 else 204)

    sender = DiscordSender({"daily": URL}, transport=httpx.MockTransport(handler), sleep=sleep)
    sender.send("daily", {"content": "hi"})
    assert len(seen) == 2
    assert seen[0].url == URL
    assert seen[0].headers["content-type"] == "application/json"
    assert b'"content":"hi"' in seen[0].content.replace(b" ", b"")
    assert delays == [1.0]


def test_send_raises_after_three_failures(no_sleep):
    sleep, delays = no_sleep
    transport = httpx.MockTransport(lambda req: httpx.Response(429))
    sender = DiscordSender({"ops": URL}, transport=transport, sleep=sleep)
    with pytest.raises(httpx.HTTPStatusError):
        sender.send("ops", {"content": "x"})
    assert delays == [1.0, 2.0]


def test_send_without_webhook_configured():
    sender = DiscordSender({})
    with pytest.raises(ValueError, match="DISCORD_WEBHOOK_ALERTS"):
        sender.send("alerts", {})
