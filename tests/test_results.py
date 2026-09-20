"""Tests for offload.results (reply classification) and the simulated limit message."""
import datetime as dt

from offload import limits, results


def test_ok_reply():
    assert results.classify({"is_error": False, "result": "done"}) == results.OK


def test_limit_reply():
    reply = {"is_error": True, "result": "You've hit your session limit · resets 7pm (America/New_York)"}
    assert results.classify(reply) == results.LIMIT


def test_overloaded_reply():
    reply = {"is_error": True, "result": "API Error: 529 Overloaded. This is a server-side issue."}
    assert results.classify(reply) == results.OVERLOADED


def test_a_529_inside_other_text_is_not_overloaded():
    reply = {"is_error": True, "result": "wrote 529 lines, then the tool failed"}
    assert results.classify(reply) == results.ERROR


def test_missing_session_reply():
    reply = {"is_error": True, "result": "No conversation found with session ID: abc"}
    assert results.classify(reply) == results.SESSION_MISSING


def test_limit_text_without_the_error_flag_is_ok():
    assert results.classify({"is_error": False, "result": "you hit your session limit"}) == results.OK


def test_is_approved():
    assert results.is_approved("APPROVE\nlooks right")
    assert results.is_approved("All tests pass, the change is minimal.\n\nAPPROVE\n- fix is correct")
    assert not results.is_approved("REQUEST_CHANGES\nAPPROVE once the test is added")
    assert not results.is_approved("I would approve this if the tests passed")
    assert not results.is_approved("")


def test_is_yes():
    assert results.is_yes("yes") and results.is_yes("Y") and results.is_yes("go ahead")
    assert not results.is_yes("no") and not results.is_yes("") and not results.is_yes(None)


def test_limit_kind():
    assert limits.limit_kind("You've hit your weekly limit · resets 3am") == "weekly"
    assert limits.limit_kind("all good") is None


def test_simulated_limit_message_round_trips_through_the_parser():
    now = dt.datetime(2026, 9, 17, 14, 0, 0).astimezone()
    message = limits.simulated_limit_message(3, now=now)
    assert limits.LIMIT_RE.search(message)
    assert limits.parse_reset(message, now=now) == now + dt.timedelta(minutes=3)
