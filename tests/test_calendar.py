from datetime import UTC, date, datetime

import pytest

from stockwatch import calendar as mcal


def test_is_trading_day_us():
    assert mcal.is_trading_day("US", date(2026, 10, 16))  # 週五
    assert not mcal.is_trading_day("US", date(2026, 10, 17))  # 週六
    assert not mcal.is_trading_day("US", date(2026, 7, 3))  # 獨立紀念日補假


def test_market_date_converts_utc_to_local():
    # 台灣 06:00 = 22:00 UTC 前一日 = 美東同日傍晚（夏令 18:00 / 冬令 17:00）
    assert mcal.market_date("US", datetime(2026, 10, 16, 22, tzinfo=UTC)) == date(2026, 10, 16)
    assert mcal.market_date("US", datetime(2026, 1, 16, 22, tzinfo=UTC)) == date(2026, 1, 16)
    # 美東 23:30 仍是同日，UTC 已是隔日
    assert mcal.market_date("US", datetime(2026, 10, 17, 3, 30, tzinfo=UTC)) == date(2026, 10, 16)


def test_market_date_rejects_naive():
    with pytest.raises(ValueError):
        mcal.market_date("US", datetime(2026, 10, 16, 22))


def test_completed_session():
    # 週五收盤後 → 當日
    assert mcal.completed_session("US", datetime(2026, 10, 16, 22, tzinfo=UTC)) == date(
        2026, 10, 16
    )
    # 週五盤中（19:00 UTC = 15:00 EDT）尚未收盤 → None
    assert mcal.completed_session("US", datetime(2026, 10, 16, 19, tzinfo=UTC)) is None
    # 週六 / 週日 → None
    assert mcal.completed_session("US", datetime(2026, 10, 17, 22, tzinfo=UTC)) is None
    assert mcal.completed_session("US", datetime(2026, 10, 18, 22, tzinfo=UTC)) is None


def test_previous_trading_day_skips_weekend():
    assert mcal.previous_trading_day("US", date(2026, 10, 19)) == date(2026, 10, 16)


def test_unknown_market():
    with pytest.raises(ValueError):
        mcal.is_trading_day("XX", date(2026, 10, 16))


def test_in_watch_window_regular_day():
    # 2026-10-16（EDT）：開盤 13:30 UTC，收盤 20:00 UTC，緩衝到 20:30 UTC
    assert not mcal.in_watch_window("US", datetime(2026, 10, 16, 13, 29, tzinfo=UTC))
    assert mcal.in_watch_window("US", datetime(2026, 10, 16, 13, 30, tzinfo=UTC))
    assert mcal.in_watch_window("US", datetime(2026, 10, 16, 20, 30, tzinfo=UTC))
    assert not mcal.in_watch_window("US", datetime(2026, 10, 16, 20, 31, tzinfo=UTC))


def test_in_watch_window_winter_time_and_weekend():
    # 2026-12-01（EST）：開盤 14:30 UTC
    assert not mcal.in_watch_window("US", datetime(2026, 12, 1, 14, 0, tzinfo=UTC))
    assert mcal.in_watch_window("US", datetime(2026, 12, 1, 14, 30, tzinfo=UTC))
    assert not mcal.in_watch_window("US", datetime(2026, 10, 17, 15, 0, tzinfo=UTC))  # 週六


def test_in_watch_window_early_close():
    # 2026-11-27 感恩節隔天 13:00 ET 收盤 = 18:00 UTC，緩衝到 18:30 UTC
    assert mcal.in_watch_window("US", datetime(2026, 11, 27, 18, 30, tzinfo=UTC))
    assert not mcal.in_watch_window("US", datetime(2026, 11, 27, 18, 31, tzinfo=UTC))
