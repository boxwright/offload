"""The files `offload init` and `offload demo` write."""

DEFAULT_BUDGET = """\
# Offload paces its Claude use against this file. Edits apply to the next call.
# Unit: USD at API list prices, as Claude Code reports per call. On a subscription it is a yardstick, not a bill.
claude:
  weekly_usd_equivalent: 150      # tune it: after a full week, ledger total / percent shown on your usage page
  allowance_percent: 60           # the engine's share of your week; the rest stays for your own sessions
  week_resets: "Tue 22:00"        # when your weekly window resets, local time (see your usage page)
  pace: even                      # spread the allowance evenly; ahead of pace, Claude steps wait
  slack_percent: 15
  models:
    plan: opus
    review: sonnet
    rescue: sonnet
  per_job:
    max_rescues: 2
escalate_when:
  failed_test_iterations: 3
  no_progress_turns: 2
"""

DEFAULT_REPOS = """\
# Repositories Offload may work on, so a one-line `offload add` can name them loosely.
#   <path or git URL>: <one line on what it is>
"""

DEFAULT_CONFIG = """\
# Offload settings. Every key is optional; `offload init --show-defaults` prints them all.
# sandbox_image: offload-sandbox:latest
# docker_network: offload_net
"""

SERVICE_UNIT = """\
[Unit]
Description=Offload daemon
After=network-online.target docker.service

[Service]
ExecStart={offload} serve
Restart=always
RestartSec=10
# A worker container ignores SIGTERM. The next start kills leftover containers, so a short stop is safe.
TimeoutStopSec=15

[Install]
WantedBy=default.target
"""

DIGEST_SERVICE_UNIT = """\
[Unit]
Description=Offload daily digest

[Service]
Type=oneshot
ExecStart={offload} digest
"""

DIGEST_TIMER_UNIT = """\
[Unit]
Description=Offload daily digest at 08:00

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
"""

DEMO_MODULE = '''\
def add(a, b):
    return a + b


def mean(xs):
    if not xs:
        raise ValueError("empty")
    return sum(xs) / (len(xs) - 1)


def median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        raise ValueError("empty")
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
'''

DEMO_TESTS = '''\
import pytest

from calc import add, mean, median


def test_add():
    assert add(2, 3) == 5


def test_mean():
    assert mean([1, 2, 3, 4]) == 2.5


def test_mean_single():
    assert mean([7]) == 7


def test_mean_empty():
    with pytest.raises(ValueError):
        mean([])


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([4, 1, 3, 2]) == 2.5
'''

DEMO_JOB = """\
---
id: {job_id}
title: Fix the failing statistics tests in the demo repository
repo: {repo}
test: python3 -m pytest -q
---
## Goal
The tests in `tests/` fail because of a defect in `calc/__init__.py`. Find and fix it without changing the tests.

## Done when
`python3 -m pytest -q` passes, the change touches only `calc/`, and the branch is pushed.
"""
