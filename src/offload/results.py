"""Classify what a worker sent back. Every text match on a worker reply lives here."""
import re

from offload.limits import LIMIT_RE

OK = "ok"
ERROR = "error"
OVERLOADED = "overloaded"
LIMIT = "limit"
SESSION_MISSING = "session_missing"

_OVERLOADED_RE = re.compile(r"API Error: 529|\b529\b[^\n]*overload|overloaded_error", re.I)
_STUCK_RE = re.compile(r"^\s*STUCK\b(?!\s*:\s*no\b)", re.M)
_VERDICT_RE = re.compile(r"\b(APPROVE|REQUEST_CHANGES)\b")
_YES_RE = re.compile(r"\s*(y|yes|ok|go)\b", re.I)


def classify(reply):
    """Sort a Claude Code result record into one of the kinds above."""
    if not reply.get("is_error"):
        return OK
    text = reply.get("result") or ""
    if LIMIT_RE.search(text):
        return LIMIT
    if _OVERLOADED_RE.search(text):
        return OVERLOADED
    if "No conversation found" in text:
        return SESSION_MISSING
    return ERROR


def is_stuck(text):
    """True when a worker's final answer opens a line with STUCK. `STUCK: no` does not count."""
    return bool(_STUCK_RE.search(text))


def is_approved(verdict):
    """True when the reply says APPROVE and nowhere says REQUEST_CHANGES.

    Reviewers are told to lead with one word, but some write a sentence first, and one wrote
    "APPROVE — no." and then REQUEST_CHANGES. A reply with both words is not an approval: a wrong
    "changes requested" costs one local session, and a wrong approval pushes a bad branch. The words
    are matched in capitals only, so "I would approve this if" does not count.
    """
    words = set(_VERDICT_RE.findall(verdict))
    return words == {"APPROVE"}


def is_yes(answer):
    return bool(answer) and bool(_YES_RE.match(answer))
