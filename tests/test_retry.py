import pytest

from stockwatch.retry import retry


def test_retry_succeeds_after_failures(no_sleep):
    sleep, delays = no_sleep
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert retry(flaky, attempts=3, base_delay=1.0, sleep=sleep) == "ok"
    assert calls["n"] == 3
    assert delays == [1.0, 2.0]  # 指數退避


def test_retry_raises_last_error_after_attempts(no_sleep):
    sleep, delays = no_sleep

    def always_fail() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        retry(always_fail, attempts=3, sleep=sleep)
    assert delays == [1.0, 2.0]


def test_retry_only_catches_listed_exceptions(no_sleep):
    sleep, delays = no_sleep

    def fail() -> None:
        raise KeyError("x")

    with pytest.raises(KeyError):
        retry(fail, attempts=3, exceptions=(ValueError,), sleep=sleep)
    assert delays == []
