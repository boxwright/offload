"""The plan-recovery ladder: a plan that comes back empty is re-asked, escalating the turn budget
and then narrowing the prompt, before the job fails with no plan steps.

`engine.claude` is faked to record the prompt and max_turns of every call; the rest of the pipeline
(local worker, test run, review) is faked for the end-to-end cases. No test touches the network,
Docker, or the real home directory.
"""
import os
import subprocess

import pytest
from conftest import make_job_dir

from offload import daemon, engine, notify, progress
from offload.files import read_jsonl, read_text
from offload.jobs import Job
from offload.prompts import plan_prompt, plan_retry_prompt

# A usable plan: two numbered steps plus the Test line.
PLAN_OK = "1. write a.txt (local-ok)\n2. write b.txt (hard)\nTest: python3 -m pytest -q\n"
# A plan that yields no steps: prose with no numbered list.
PLAN_EMPTY = "I could not produce a plan.\n"


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    """Isolated config (ledger and budget file in tmp_path), and no webhook post."""
    monkeypatch.setattr(notify, "post", lambda text: (False, "test"))
    daemon._finished.clear()


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path):
    """A bare repository with one commit, so the engine can clone and push for real."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-q", "-b", "main", cwd=seed)
    (seed / "README").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed", cwd=seed)
    bare = tmp_path / "origin.git"
    _git("clone", "-q", "--bare", str(seed), str(bare), cwd=tmp_path)
    return str(bare)


def _write_budget(settings, max_plan_attempts):
    """Point the job's budget file at a `max_plan_attempts` value so the ladder reads it."""
    with open(settings.budget_file, "w") as f:
        f.write(f"claude:\n  per_job:\n    max_plan_attempts: {max_plan_attempts}\n")


def _events_by_kind(job_dir):
    rows = list(read_jsonl(os.path.join(job_dir, "events.jsonl"), strict=False))
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get("kind"), []).append(row)
    return grouped


class Fakes:
    """Fake workers. `claude` records the prompt and max_turns of every call and answers the plan
    calls from a script; the review call is approved and the local worker writes its step's file."""

    def __init__(self, monkeypatch, plan_replies):
        self.claude_calls = []       # (purpose, prompt, max_turns) in call order
        self._plan_replies = list(plan_replies)
        self.local_purposes = []
        monkeypatch.setattr(engine, "claude", self.claude)
        monkeypatch.setattr(engine, "local_harness", self.local)
        monkeypatch.setattr(engine, "run_tests", lambda job: (True, ""))
        monkeypatch.setattr(engine, "step_brief", lambda job, step, plan_text, feedback: step)

    def claude(self, job, prompt, model, max_turns, purpose, tools=None):
        self.claude_calls.append((purpose, prompt, max_turns))
        if purpose == "plan":
            return self._plan_replies.pop(0)
        return "APPROVE", {}

    def local(self, job, brief, purpose):
        self.local_purposes.append(purpose)
        name = brief.split()[-1]
        with open(os.path.join(job.work, name), "w") as f:
            f.write(purpose)
        return "done", {"worker": "fake", "wall_s": 0}


# ---------------------------------------------------------------- the ladder, in isolation
def test_a_first_retry_recovers_the_plan(job_factory, monkeypatch):
    """An empty first attempt is re-asked with a wider turn budget; the retry's plan is kept."""
    job = Job(job_factory("p1", {"id": "p1"}))
    fakes = Fakes(monkeypatch, [(PLAN_EMPTY, {}), (PLAN_OK, {})])
    plan_text, steps = engine._plan(job)

    assert steps == ["1. write a.txt (local-ok)", "2. write b.txt (hard)"]
    # two plan calls: the empty first attempt, then the retry
    assert [c[0] for c in fakes.claude_calls] == ["plan", "plan"]
    # the retry widens the turn budget
    assert fakes.claude_calls[0][2] == 20 and fakes.claude_calls[1][2] > 20
    # both attempts use the full planner prompt (the narrowed one is a later retry)
    assert fakes.claude_calls[0][1] == plan_prompt(job)
    assert fakes.claude_calls[1][1] == plan_prompt(job)
    # one plan_attempt event per attempt, carrying the attempt number, reason and max_turns
    attempts = _events_by_kind(job.dir)["plan_attempt"]
    assert [(a["attempt"], a["reason"], a["max_turns"]) for a in attempts] == [
        (1, "first attempt", 20),
        (2, "previous attempt had no steps", 30)]
    # the plan is recorded and the job moves on to its steps
    assert read_text(job.path("plan.txt")) == PLAN_OK
    assert progress.load(job)["phase"] == progress.STEPS


def test_a_narrowed_second_retry_recovers_the_plan(job_factory, settings, monkeypatch):
    """When the first retry is also empty, the second retry asks the narrowed question."""
    _write_budget(settings, 3)
    job = Job(job_factory("p2", {"id": "p2"}))
    fakes = Fakes(monkeypatch, [(PLAN_EMPTY, {}), (PLAN_EMPTY, {}), (PLAN_OK, {})])
    plan_text, steps = engine._plan(job)

    assert len(steps) == 2
    assert len(fakes.claude_calls) == 3
    # the first two attempts are the full prompt; the second retry is the narrowed re-ask
    assert fakes.claude_calls[0][1] == plan_prompt(job)
    assert fakes.claude_calls[1][1] == plan_prompt(job)
    assert fakes.claude_calls[2][1] == plan_retry_prompt(job)
    # the retry keeps the widened budget
    assert fakes.claude_calls[1][2] == fakes.claude_calls[2][2] > fakes.claude_calls[0][2]


def test_the_plan_attempt_cap_comes_from_the_budget_file(job_factory, settings, monkeypatch):
    """`max_plan_attempts` in the budget file, not a hardcoded two, bounds the ladder."""
    _write_budget(settings, 4)
    job = Job(job_factory("p4", {"id": "p4"}))
    fakes = Fakes(monkeypatch, [(PLAN_EMPTY, {})] * 4)
    plan_text, steps = engine._plan(job)

    assert steps == []
    # four attempts because the budget file says four
    assert len(fakes.claude_calls) == 4
    assert [a["attempt"] for a in _events_by_kind(job.dir)["plan_attempt"]] == [1, 2, 3, 4]


# ---------------------------------------------------------------- end to end
def test_exhausted_attempts_fail_the_job_with_no_plan_steps(tmp_path, origin, monkeypatch):
    """When every attempt is empty, the job fails with no plan steps and EXIT_SETUP."""
    fakes = Fakes(monkeypatch, [(PLAN_EMPTY, {}), (PLAN_EMPTY, {})])
    job_dir = make_job_dir(tmp_path, "exhausted", {"id": "exhausted", "repo": origin})

    assert engine.run(job_dir) == engine.EXIT_SETUP
    # exactly the default number of plan attempts, all empty
    assert [c[0] for c in fakes.claude_calls] == ["plan", "plan"]
    fails = _events_by_kind(job_dir)["fail"]
    assert fails and fails[-1]["reason"] == "no plan steps"


def test_plan_attempt_events_reach_the_report(tmp_path, origin, monkeypatch):
    """A self-rescued plan is visible in REPORT.md: the attempt count and one line per attempt."""
    Fakes(monkeypatch, [(PLAN_EMPTY, {}), (PLAN_OK, {})])
    job_dir = make_job_dir(tmp_path / "jobs", "rec", {"id": "rec", "repo": origin})

    daemon._run_and_report(job_dir)
    report = read_text(os.path.join(job_dir, "REPORT.md"))
    # the plan line notes the self-rescue, and each attempt is its own line
    assert "2 attempts" in report
    assert "plan attempt 1" in report
    assert "plan attempt 2" in report
