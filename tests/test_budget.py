"""Tests for the engine's budget pacer: ledger_add / spent_since / job_cost round trip
and pace_status (empty ledger, far above even pace, at/above allowance).

The ledger and budget file are redirected into tmp_path via the api_isolated
fixture, so no test touches the real home directory, the network, or Docker.
Every `now` is an explicit tz-aware datetime and every ledger `ts` is seeded
explicitly, so the tests are deterministic and never depend on the wall clock.
"""
import datetime as dt
import json
import os
import time

import pytest

UTC = dt.timezone.utc

# A Thursday, mid-week, well inside the Tue 22:00 -> next Tue 22:00 window.
NOW = dt.datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
# allowance = 150 * 60 / 100 = 90.0
B = {"claude": {"weekly_usd_equivalent": 150, "allowance_percent": 60,
                "week_resets": "Tue 22:00", "pace": "even", "slack_percent": 15}}


def _seed_ledger(ledger, ts, usd, job="j-x", model="sonnet"):
    """Write one ledger record with an explicit ts (so it is or is not counted
    deterministically) into the tmp_path ledger."""
    with open(ledger, "w") as f:
        f.write(json.dumps({"t": "2026-09-17 10:00:00", "ts": ts, "job": job,
                            "model": model, "purpose": "plan", "usd": usd,
                            "cache_read": 0, "output_tokens": 0}) + "\n")


# ---------------------------------------------------------------- round trip
def test_ledger_add_writes_record(api_isolated, job_factory, settings, tmp_path):
    """ledger_add appends one JSON line to the tmp_path ledger with all fields."""
    d = job_factory(name="j-budget", meta={"id": "j-budget", "repo": "/srv/repos/demo"})
    job = api_isolated.Job(d)
    api_isolated.ledger_add(job, "sonnet", "plan", 1.25, 1000, 200)
    with open(settings.ledger) as f:
        rec = json.loads(f.readline())
    assert rec["job"] == "j-budget"
    assert rec["model"] == "sonnet"
    assert rec["purpose"] == "plan"
    assert rec["usd"] == 1.25
    assert rec["cache_read"] == 1000
    assert rec["output_tokens"] == 200
    assert "ts" in rec and "t" in rec
    # the ledger lives under this test's tmp_path, never the real home
    assert os.path.dirname(settings.ledger) == str(tmp_path)


def test_ledger_add_spent_since_job_cost_round_trip(api_isolated, job_factory):
    """ledger_add -> spent_since / job_cost read the same records back, filtered by job."""
    d = job_factory(name="j-budget", meta={"id": "j-budget", "repo": "/srv/repos/demo"})
    job = api_isolated.Job(d)
    api_isolated.ledger_add(job, "opus", "plan", 2.50, 1000, 300)
    api_isolated.ledger_add(job, "sonnet", "review", 1.50, 500, 150)
    # a second job, to prove job_cost filters by id
    d2 = job_factory(name="j-other", meta={"id": "j-other", "repo": "/srv/repos/demo"})
    job2 = api_isolated.Job(d2)
    api_isolated.ledger_add(job2, "sonnet", "plan", 0.75, 100, 50)

    # spent_since(0) counts every record (ts >= 0 is always true)
    assert api_isolated.spent_since(0.0) == pytest.approx(4.75)

    # job_cost for j-budget: total 4.0, split across the two models used
    total, per = api_isolated.job_cost("j-budget")
    assert total == pytest.approx(4.00)
    assert per == {"opus": 2.50, "sonnet": 1.50}

    # job_cost for j-other: only its own record
    total2, per2 = api_isolated.job_cost("j-other")
    assert total2 == pytest.approx(0.75)
    assert per2 == {"sonnet": 0.75}

    # an unknown job: empty
    total3, per3 = api_isolated.job_cost("j-none")
    assert total3 == 0.0 and per3 == {}


def test_spent_since_future_ts_counts_nothing(api_isolated, job_factory):
    """A cutoff ts after every record's ts counts nothing."""
    d = job_factory(name="j-budget", meta={"id": "j-budget", "repo": "/srv/repos/demo"})
    job = api_isolated.Job(d)
    api_isolated.ledger_add(job, "sonnet", "plan", 1.25, 1000, 200)
    assert api_isolated.spent_since(time.time() + 86400) == 0.0


def test_spent_since_missing_ledger_returns_zero(api_isolated, settings):
    """No ledger file yet -> spent_since is 0.0, not an exception."""
    assert not os.path.exists(settings.ledger)
    assert api_isolated.spent_since(0.0) == 0.0


# ---------------------------------------------------------------- pace_status
def test_pace_status_empty_ledger_allowed(api_isolated, settings):
    """An empty (missing) ledger is within pace: allowed now, zero wait."""
    assert not os.path.exists(settings.ledger)
    allowed, spent, pace_now, allowance, secs = api_isolated.pace_status(B, now=NOW)
    assert allowed is True
    assert spent == 0.0
    assert allowance == pytest.approx(90.0)
    assert secs == 0
    assert 0 < pace_now < allowance  # some of the week has elapsed, so pace_now > 0


def test_pace_status_far_above_pace_not_allowed(api_isolated, settings):
    """Spend far above even pace (but under allowance) is not allowed: positive wait."""
    ws = api_isolated.week_start(B, now=NOW)
    _seed_ledger(settings.ledger, ws.timestamp() + 10, 50.0)
    allowed, spent, pace_now, allowance, secs = api_isolated.pace_status(B, now=NOW)
    assert allowed is False
    assert spent == pytest.approx(50.0)
    assert allowance == pytest.approx(90.0)
    assert secs > 0  # a positive wait is scheduled until even pace catches up


def test_pace_status_at_allowance_not_allowed(api_isolated, settings):
    """Spend exactly at the weekly allowance is not allowed."""
    ws = api_isolated.week_start(B, now=NOW)
    _seed_ledger(settings.ledger, ws.timestamp() + 10, 90.0)
    allowed, spent, pace_now, allowance, secs = api_isolated.pace_status(B, now=NOW)
    assert allowed is False
    assert spent == pytest.approx(90.0)
    assert allowance == pytest.approx(90.0)
    assert secs > 0


def test_pace_status_above_allowance_not_allowed(api_isolated, settings):
    """Spend above the weekly allowance is not allowed."""
    ws = api_isolated.week_start(B, now=NOW)
    _seed_ledger(settings.ledger, ws.timestamp() + 10, 95.0)
    allowed, spent, pace_now, allowance, secs = api_isolated.pace_status(B, now=NOW)
    assert allowed is False
    assert spent == pytest.approx(95.0)
    assert allowance == pytest.approx(90.0)
    assert secs > 0


def test_a_damaged_ledger_line_is_skipped(api_isolated, job_factory, settings):
    """A line cut short by a crash must not stop the pacer."""
    job = api_isolated.Job(job_factory("j-1", meta={"id": "j-1", "repo": "/r.git"}))
    api_isolated.ledger_add(job, "sonnet", "review", 0.25, 1000, 50)
    with open(settings.ledger, "a") as f:
        f.write('{"t": "2026-01-01 00:00:00", "ts": 1, "usd": 9')      # truncated
    assert api_isolated.spent_since(0) == 0.25
    assert api_isolated.job_cost("j-1")[0] == 0.25
