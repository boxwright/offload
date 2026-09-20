"""Tests for the engine's pure time logic: parse_reset and week_start.

Every `now` is an explicit tz-aware datetime, so the tests are
deterministic and never call datetime.now(). No file, network, or
Docker access is involved.
"""
import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def test_parse_reset_same_day_7pm_new_york(api):
    """'resets 7pm (America/New_York)' before 7pm lands on the same day."""
    now = dt.datetime(2026, 9, 17, 14, 0, 0, tzinfo=NY)  # a Thursday, 2pm ET
    got = api.parse_reset("You've hit your session limit · resets 7pm (America/New_York)", now=now)
    assert got == dt.datetime(2026, 9, 17, 19, 0, 0, tzinfo=NY)


def test_parse_reset_past_time_rolls_to_tomorrow(api):
    """'resets 7pm (America/New_York)' after 7pm rolls to the next day."""
    now = dt.datetime(2026, 9, 17, 20, 0, 0, tzinfo=NY)  # 8pm ET, 7pm already past
    got = api.parse_reset("You've hit your session limit · resets 7pm (America/New_York)", now=now)
    assert got == dt.datetime(2026, 9, 18, 19, 0, 0, tzinfo=NY)


def test_parse_reset_330am(api):
    """'resets 3:30am' parses hour and minute in the caller's tz."""
    now = dt.datetime(2026, 9, 17, 2, 0, 0, tzinfo=UTC)  # 2am UTC, before 3:30
    got = api.parse_reset("You've hit your session limit · resets 3:30am", now=now)
    assert got == dt.datetime(2026, 9, 17, 3, 30, 0, tzinfo=UTC)


def test_parse_reset_in_45_minutes(api):
    """'resets in 45 minutes' is a plain offset from now."""
    now = dt.datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
    got = api.parse_reset("You've hit your session limit · resets in 45 minutes", now=now)
    assert got == dt.datetime(2026, 9, 17, 12, 45, 0, tzinfo=UTC)


def test_parse_reset_no_reset_returns_none(api):
    """A limit message without a reset time yields None."""
    now = dt.datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
    assert api.parse_reset("You've hit your session limit", now=now) is None


def test_week_start_thursday_gives_previous_tuesday_22(api):
    """Thursday now with week_resets 'Tue 22:00' -> previous Tuesday 22:00."""
    b = {"claude": {"week_resets": "Tue 22:00"}}
    now = dt.datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)  # Thursday
    assert now.weekday() == 3
    got = api.week_start(b, now=now)
    assert got == dt.datetime(2026, 9, 15, 22, 0, 0, tzinfo=UTC)  # Tuesday


def test_week_start_tuesday_2100_gives_tuesday_a_week_earlier(api):
    """Tuesday 21:00 now is before the 22:00 reset -> Tuesday a week earlier."""
    b = {"claude": {"week_resets": "Tue 22:00"}}
    now = dt.datetime(2026, 9, 15, 21, 0, 0, tzinfo=UTC)  # Tuesday
    assert now.weekday() == 1
    got = api.week_start(b, now=now)
    assert got == dt.datetime(2026, 9, 8, 22, 0, 0, tzinfo=UTC)  # a week earlier
