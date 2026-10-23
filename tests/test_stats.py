from datetime import date, timedelta

from stockwatch.datasource import DailyBar
from stockwatch.report.stats import compute_stat


def _bars(n: int, *, last: date, close_start: float = 100.0, volume: int = 1_000) -> list[DailyBar]:
    bars = []
    for i in range(n):
        d = last - timedelta(days=n - 1 - i)
        c = close_start + i
        bars.append(DailyBar("T", d, c, c + 1, c - 1, c, volume))
    return bars


def test_compute_stat_pct_and_volume_multiple():
    last = date(2026, 10, 16)
    bars = _bars(21, last=last)
    bars[-1] = DailyBar("T", last, 120, 121, 119, 121.0, 3_000)  # 當日量 3 倍
    stat = compute_stat("T", bars, last)
    assert stat is not None
    assert stat.prev_close == 119.0
    assert stat.pct_change == (121.0 / 119.0 - 1.0)
    assert stat.vol_avg20 == 1_000
    assert stat.vol_multiple == 3.0


def test_compute_stat_without_enough_volume_history():
    last = date(2026, 10, 16)
    stat = compute_stat("T", _bars(5, last=last), last)
    assert stat is not None
    assert stat.pct_change is not None
    assert stat.vol_avg20 is None
    assert stat.vol_multiple is None


def test_compute_stat_single_bar_has_no_change():
    last = date(2026, 10, 16)
    stat = compute_stat("T", _bars(1, last=last), last)
    assert stat is not None
    assert stat.prev_close is None
    assert stat.pct_change is None


def test_compute_stat_returns_none_when_no_bar_for_report_date():
    last = date(2026, 10, 15)
    assert compute_stat("T", _bars(5, last=last), date(2026, 10, 16)) is None
    assert compute_stat("T", [], date(2026, 10, 16)) is None
