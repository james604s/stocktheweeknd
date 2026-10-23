import json
import traceback
from datetime import UTC, datetime

import httpx
import pytest

from stockwatch.datasource.finnhub_source import (
    FinnhubError,
    FinnhubSource,
    quote_from_json,
)

KEY = "FAKE_FINNHUB_KEY_123"


def _fixture(fixtures_dir, name: str) -> dict:
    return json.loads((fixtures_dir / name).read_text())


def test_quote_from_fixture(fixtures_dir):
    q = quote_from_json("NVDA", _fixture(fixtures_dir, "finnhub_quote_NVDA.json"))
    assert q.price == 189.42
    assert q.prev_close == 178.6
    assert q.ts == datetime(2026, 10, 16, 15, 0, tzinfo=UTC)
    assert q.day_volume is None


def test_unknown_symbol_returns_zeros(fixtures_dir):
    with pytest.raises(FinnhubError, match="沒有 XXXX 的報價"):
        quote_from_json("XXXX", _fixture(fixtures_dir, "finnhub_quote_unknown.json"))


def test_get_quote_sends_token_in_header_not_url(fixtures_dir, no_sleep):
    sleep, _ = no_sleep
    seen: list[httpx.Request] = []
    body = _fixture(fixtures_dir, "finnhub_quote_NVDA.json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=body)

    src = FinnhubSource(KEY, transport=httpx.MockTransport(handler), sleep=sleep)
    assert src.get_quote("NVDA").price == 189.42
    assert seen[0].url.path == "/api/v1/quote"
    assert seen[0].url.params["symbol"] == "NVDA"
    assert seen[0].headers["X-Finnhub-Token"] == KEY
    assert KEY not in str(seen[0].url)


def test_retries_on_429_and_5xx(fixtures_dir, no_sleep):
    sleep, delays = no_sleep
    body = _fixture(fixtures_dir, "finnhub_quote_NVDA.json")
    responses = [httpx.Response(429), httpx.Response(502), httpx.Response(200, json=body)]
    src = FinnhubSource(KEY, transport=httpx.MockTransport(lambda r: responses.pop(0)), sleep=sleep)
    assert src.get_quote("NVDA").price == 189.42
    assert delays == [1.0, 2.0]


def test_401_not_retried_and_errors_hide_key(no_sleep):
    sleep, delays = no_sleep

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"invalid token {KEY}")

    def conn_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {KEY}", request=request)

    for handler in (unauthorized, conn_error):
        src = FinnhubSource(KEY, transport=httpx.MockTransport(handler), sleep=sleep)
        with pytest.raises(FinnhubError) as info:
            src.get_quote("NVDA")
        assert KEY not in "".join(traceback.format_exception(info.value))
    assert delays == [1.0, 2.0]  # 只有連線錯誤會重試


def test_requires_key():
    with pytest.raises(ValueError, match="FINNHUB_KEY"):
        FinnhubSource("")
