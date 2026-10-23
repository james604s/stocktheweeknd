from datetime import UTC, date, datetime, timedelta

import pytest

from stockwatch.datasource import DailyBar, Quote
from stockwatch.rules.builtin import (
    GREEN,
    GREY,
    RED,
    pct_change_vs_prev_close,
    volume_multiple,
    volume_vs_avg20,
)

TS = datetime(2026, 10, 16, 15, 0, tzinfo=UTC)


def _quote(price: float, prev: float = 100.0, volume: int | None = 1_000) -> Quote:
    return Quote("NVDA", TS, price, prev, volume)


def _history(n: int = 20, volume: int = 1_000) -> list[DailyBar]:
    start = date(2026, 9, 1)
    return [
        DailyBar("NVDA", start + timedelta(days=i), 100, 101, 99, 100, volume) for i in range(n)
    ]


PCT = pct_change_vs_prev_close(rule_id="pct_move_5", threshold=0.05, channels=("alerts",))
VOL = volume_vs_avg20(rule_id="vol_spike_2x", multiplier=2.0, channels=("alerts",))


def test_pct_rule_up_hit():
    p = PCT("NVDA", _quote(106.2), _history())
    assert p is not None
    assert p.title == "NVDA ▲ +6.2%"
    assert p.color == GREEN
    assert p.fields == {
        "現價": "106.20",
        "前收": "100.00",
        "成交量倍數": "1.0x",
        "觸發規則": "pct_move_5",
    }
    assert p.channels == ("alerts",)


def test_pct_rule_down_hit_and_threshold_inclusive():
    p = PCT("NVDA", _quote(95.0), _history())
    assert p is not None and p.title == "NVDA ▼ -5.0%" and p.color == RED


def test_pct_rule_below_threshold():
    assert PCT("NVDA", _quote(104.9), _history()) is None
    assert PCT("NVDA", _quote(95.1), _history()) is None


def test_pct_rule_without_prev_close():
    assert PCT("NVDA", _quote(120.0, prev=0.0), _history()) is None


def test_volume_rule_hit_shows_pct_in_title():
    p = VOL("NVDA", _quote(101.0, volume=2_500), _history())
    assert p is not None
    assert p.title == "NVDA ▲ +1.0%"
    assert p.fields["成交量倍數"] == "2.5x"
    assert p.fields["觸發規則"] == "vol_spike_2x"


def test_volume_rule_flat_price_is_grey():
    p = VOL("NVDA", _quote(100.0, volume=3_000), _history())
    assert p is not None and p.color == GREY and p.title == "NVDA ─ +0.0%"


def test_volume_rule_misses():
    assert VOL("NVDA", _quote(100.0, volume=1_999), _history()) is None
    assert VOL("NVDA", _quote(100.0, volume=None), _history()) is None  # 成交量暫缺
    assert VOL("NVDA", _quote(100.0, volume=9_999), _history(19)) is None  # 歷史不足 20 日


def test_volume_multiple_uses_last_20_bars():
    history = _history(5, volume=10) + _history(20, volume=1_000)
    assert volume_multiple(_quote(100, volume=2_000), history) == 2.0


def test_rules_are_pure_and_deterministic():
    q, h = _quote(110.0, volume=5_000), _history()
    assert PCT("NVDA", q, h) == PCT("NVDA", q, h)
    assert VOL("NVDA", q, h) == VOL("NVDA", q, h)


def test_invalid_parameters():
    with pytest.raises(ValueError):
        pct_change_vs_prev_close(rule_id="x", threshold=0, channels=("alerts",))
    with pytest.raises(ValueError, match="basis"):
        volume_vs_avg20(rule_id="x", multiplier=2, channels=("alerts",), basis="prorated")
