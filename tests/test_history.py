from datetime import date

from stockwatch.datasource import DailyBar
from stockwatch.history import history_revised


def _bar(day: int, close: float) -> DailyBar:
    return DailyBar("T", date(2026, 10, day), close, close, close, close, 100)


def test_identical_history_is_not_revised():
    stored = [_bar(13, 100.0), _bar(14, 101.0)]
    assert history_revised(stored, [_bar(13, 100.0), _bar(14, 101.0), _bar(15, 102.0)]) is False


def test_small_revision_within_tolerance():
    assert history_revised([_bar(13, 100.0)], [_bar(13, 100.5)]) is False


def test_split_detected():
    assert history_revised([_bar(13, 100.0)], [_bar(13, 10.0)]) is True  # 10:1
    assert history_revised([_bar(13, 100.0)], [_bar(13, 80.0)]) is True  # 5:4
    assert history_revised([_bar(13, 10.0)], [_bar(13, 100.0)]) is True  # 反向分割


def test_no_overlap_is_not_revised():
    assert history_revised([_bar(13, 100.0)], [_bar(14, 10.0)]) is False
    assert history_revised([], [_bar(14, 10.0)]) is False
