import numpy as np
import pandas as pd

from touchmkt import build

UTC = "UTC"


def mk(desc, end):
    return {"description": desc, "end": end}


def test_window_daily_with_start_time():
    d = "resolve to Yes if any Binance 1-minute candle ... on the date specified in the title, between 9:30 AM ET and 11:59 PM ET has a final High"
    s, e = build.window(mk(d, "2025-08-16T04:00:00Z"), "What price will Bitcoin hit on August 15?")
    assert s == pd.Timestamp("2025-08-15 13:30", tz=UTC) and e == pd.Timestamp("2025-08-16 04:00", tz=UTC)
    # A scheduled end an hour late (around a clock change) still ends the window at midnight ET.
    _, e2 = build.window(mk(d, "2026-03-09T05:00:00Z"), "x")
    assert e2 == pd.Timestamp("2026-03-09 04:00", tz=UTC)


def test_window_explicit_dates_and_new_weekly_and_monthly_wording():
    d = 'candle for Bitcoin (BTC/USDT) between July 9, 2025, 10:00 and July 13, 2025, 23:59 in the ET timezone'
    s, _ = build.window(mk(d, "2025-07-14T04:00:00Z"), "x")
    assert s == pd.Timestamp("2025-07-09 14:00", tz=UTC)
    d = "during the date range specified in the title (from 12:00 AM ET on the first date to 11:59 PM ET on the last)"
    s, _ = build.window(mk(d, "2026-11-02T05:00:00Z"), "What price will Bitcoin hit October 26-November 1?")
    assert s == pd.Timestamp("2026-10-26 04:00", tz=UTC)
    d = "during the month specified in the title (from 00:00 AM ET on the first day to 11:59 PM ET on the last)"
    s, _ = build.window(mk(d, "2026-11-01T04:00:00Z"), "What price will Bitcoin hit in October?")
    assert s == pd.Timestamp("2026-10-01 04:00", tz=UTC)
    assert build.window(mk("no recognizable wording", "2026-11-01T04:00:00Z"), "x") is None


def test_window_weekly_across_new_year():
    d = "(from 12:00 AM ET on the first date to 11:59 PM ET on the last)"
    s, _ = build.window(mk(d, "2026-01-05T05:00:00Z"), "What price will Bitcoin hit December 29-January 4?")
    assert s == pd.Timestamp("2025-12-29 05:00", tz=UTC)


def test_first_touch_finds_first_bar_in_window_only():
    idx = pd.date_range("2026-01-01", periods=10, freq="min", tz=UTC)
    bars = pd.DataFrame({"high": [100, 101, 106, 99, 107, 100, 100, 100, 100, 100.0],
                         "low": [99, 95, 99, 99, 99, 99, 90, 99, 99, 99.0]}, index=idx)
    m = pd.DataFrame([
        {"direction": "reach", "strike": 105.0, "start": idx[3], "end": idx[9]},  # the bar at 2 is before the window
        {"direction": "dip", "strike": 96.0, "start": idx[0], "end": idx[9]},
        {"direction": "reach", "strike": 110.0, "start": idx[0], "end": idx[9]},
    ])
    ft = build.first_touch(m, bars)
    assert ft[0] == idx[4] and ft[1] == idx[1] and pd.isna(ft[2])


def test_window_later_wordings():
    d = "during the date range specified in the title (from 5:00 AM ET on the first date to 11:59 PM ET on the last)"
    s, _ = build.window(mk(d, "2025-09-08T04:00:00Z"), "What price will Bitcoin hit September 1-7?")
    assert s == pd.Timestamp("2025-09-01 09:00", tz=UTC)
    d = "any Binance 1 minute candle for BTC/USDT from the creation of this market through 11:59 PM ET on the last day of the month"
    m = mk(d, "2026-08-01T04:00:00Z") | {"start": "2026-06-24T15:00:00Z"}
    s, _ = build.window(m, "What price will Bitcoin hit in July?")
    assert s == pd.Timestamp("2026-06-24 15:00", tz=UTC)


def test_strike_suffix_ignores_month_names():
    from touchmkt.download import parse_question
    assert parse_question("Will Bitcoin dip to $54,000 March 30-April 5?") == ("dip", 54000.0)
    assert parse_question("Will Bitcoin reach $114K before July 14?") == ("reach", 114000.0)
    assert parse_question("Will Bitcoin reach $1M in 2025?") == ("reach", 1000000.0)
