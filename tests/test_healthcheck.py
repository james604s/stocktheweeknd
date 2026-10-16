import logging

import httpx

from stockwatch.healthcheck import ping

URL = "https://hc-ping.com/SECRET-UUID"


def test_ping_success_and_fail_suffix(no_sleep):
    sleep, _ = no_sleep
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    t = httpx.MockTransport(handler)
    assert ping(URL, transport=t, sleep=sleep) is True
    assert ping(URL, fail=True, transport=t, sleep=sleep) is True
    assert seen == [URL, URL + "/fail"]


def test_ping_failure_is_logged_without_url(no_sleep, caplog):
    sleep, delays = no_sleep
    t = httpx.MockTransport(lambda req: httpx.Response(503))
    with caplog.at_level(logging.WARNING):
        assert ping(URL, transport=t, sleep=sleep) is False
    assert delays == [1.0, 2.0]
    assert "SECRET-UUID" not in caplog.text
