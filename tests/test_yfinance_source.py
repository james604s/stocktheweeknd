from datetime import date

import pandas as pd
import pytest

from stockwatch.datasource.yfinance_source import YFinanceSource, bars_from_frame


def _load(fixtures_dir) -> pd.DataFrame:
    df = pd.read_csv(fixtures_dir / "yfinance_NVDA_daily.csv")
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert("America/New_York")
    return df.set_index("Date")


def test_bars_from_fixture_frame(fixtures_dir):
    bars = bars_from_frame("NVDA", _load(fixtures_dir))
    assert len(bars) == 25
    assert bars[0].date == date(2026, 9, 14)
    assert bars[-1].date == date(2026, 10, 16)
    assert bars[-1].ticker == "NVDA"
    assert isinstance(bars[-1].volume, int)
    assert bars[-1].high >= bars[-1].close >= bars[-1].low


def test_bars_from_frame_skips_nan_rows(fixtures_dir):
    df = _load(fixtures_dir)
    df.loc[df.index[0], "Close"] = float("nan")
    assert len(bars_from_frame("NVDA", df)) == 24


def test_bars_from_empty_frame():
    assert bars_from_frame("NVDA", pd.DataFrame()) == []


def test_get_daily_bars_retries_then_succeeds(fixtures_dir, no_sleep):
    sleep, delays = no_sleep
    frame = _load(fixtures_dir)
    calls: list[tuple[str, date, date]] = []

    def fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((ticker, start, end))
        if len(calls) == 1:
            raise ConnectionError("yahoo down")
        return frame

    source = YFinanceSource(fetch=fetch, sleep=sleep)
    bars = source.get_daily_bars("NVDA", date(2026, 9, 14), date(2026, 10, 16))
    assert len(bars) == 25
    assert len(calls) == 2
    assert delays == [1.0]


def test_get_daily_bars_gives_up_after_three(no_sleep):
    sleep, delays = no_sleep

    def fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        raise ConnectionError("yahoo down")

    source = YFinanceSource(fetch=fetch, sleep=sleep)
    with pytest.raises(ConnectionError):
        source.get_daily_bars("NVDA", date(2026, 9, 14), date(2026, 10, 16))
    assert delays == [1.0, 2.0]
