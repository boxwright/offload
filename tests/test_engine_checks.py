"""The spec checks: run once each after the push, one `check` event per command, and a `fail`
with reason `checks` when one exits non-zero — the branch is already pushed by then.

The two workers and the test run are faked (as in test_parking); `run_command` is faked so no
sandbox is needed. Job dirs and the origin live under tmp_path, so no test touches the network
or Docker.
"""
import json
import os
import subprocess

import pytest
from conftest import make_job_dir

from offload import daemon, engine, notify

PLAN_TEXT = "1. write a.txt\n2. write b.txt\n3. write c.txt\n"


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    """No webhook post, and the ledger and the budget file live in tmp_path."""
    monkeypatch.setattr(notify, "post", lambda text: (False, "test"))
    daemon._finished.clear()


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path):
    """A bare repository with one commit."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "-q", "-b", "main", cwd=seed)
    (seed / "README").write_text("seed\n")
    _git("add", "-A", cwd=seed)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "seed", cwd=seed)
    bare = tmp_path / "origin.git"
    _git("clone", "-q", "--bare", str(seed), str(bare), cwd=tmp_path)
    return str(bare)


class Fakes:
    """Stand-ins for the two workers and the test run. Each local step writes the file its brief names."""

    def __init__(self, monkeypatch):
        self.claude_purposes = []
        self.local_purposes = []
        monkeypatch.setattr(engine, "claude", self.claude)
        monkeypatch.setattr(engine, "local_harness", self.local)
        monkeypatch.setattr(engine, "run_tests", lambda job: (True, ""))
        monkeypatch.setattr(engine, "step_brief", lambda job, step, plan_text, feedback: step)

    def claude(self, job, prompt, model, max_turns, purpose, tools=None):
        self.claude_purposes.append(purpose)
        return (PLAN_TEXT if purpose == "plan" else "APPROVE"), {}

    def local(self, job, brief, purpose):
        self.local_purposes.append(purpose)
        name = brief.split()[-1]
        with open(os.path.join(job.work, name), "w") as f:
            f.write(purpose)
        return "done", {"worker": "fake", "wall_s": 0}


def _events(job_dir):
    with open(os.path.join(job_dir, "events.jsonl")) as f:
        return [json.loads(line) for line in f if line.strip()]


def _checks(job_dir):
    return [row for row in _events(job_dir) if row["kind"] == "check"]


def test_all_checks_pass_and_the_job_is_done(tmp_path, origin, monkeypatch):
    """Every check exits 0: one `check` event per command, then the `done` event and EXIT_OK."""
    Fakes(monkeypatch)
    monkeypatch.setattr(engine, "run_command", lambda job, command: (0, f"ok {command}\n", "", 0.1))
    job_dir = make_job_dir(tmp_path, "ok", {"id": "ok", "repo": origin, "checks": "[make lint, make test]"})
    assert engine.run(job_dir) == engine.EXIT_OK
    checks = _checks(job_dir)
    assert [row["command"] for row in checks] == ["make lint", "make test"]
    assert all(row["exit"] == 0 for row in checks)
    assert any(row["kind"] == "done" for row in _events(job_dir))
    branches = subprocess.run(["git", "branch", "--list"], cwd=origin, capture_output=True, text=True).stdout
    assert "offload/ok" in branches


def test_a_failing_check_fails_the_job_but_the_branch_is_pushed(tmp_path, origin, monkeypatch):
    """A non-zero check: `fail` with reason `checks`, EXIT_CHECKS, no `done` — yet the branch is on the origin."""
    fakes = Fakes(monkeypatch)
    seen = []

    def run_command(job, command):
        seen.append(command)
        if command == "make test":
            return 1, "FAIL: 2 tests failed\n", "", 0.2
        return 0, "ok\n", "", 0.1
    monkeypatch.setattr(engine, "run_command", run_command)
    job_dir = make_job_dir(tmp_path, "bad", {"id": "bad", "repo": origin, "checks": "[make lint, make test]"})
    assert engine.run(job_dir) == engine.EXIT_CHECKS
    checks = _checks(job_dir)
    assert [row["command"] for row in checks] == ["make lint", "make test"]
    assert [row["exit"] for row in checks] == [0, 1]
    assert "FAIL: 2 tests failed" in checks[1]["output"]
    fails = [row for row in _events(job_dir) if row["kind"] == "fail"]
    assert fails and "checks" in fails[-1]["reason"]
    assert not any(row["kind"] == "done" for row in _events(job_dir))
    # the push happened before the checks, so the branch is on the origin
    branches = subprocess.run(["git", "branch", "--list"], cwd=origin, capture_output=True, text=True).stdout
    assert "offload/bad" in branches
    # no retry: every check ran exactly once, and the failure made no further Claude call
    assert seen == ["make lint", "make test"]
    assert fakes.claude_purposes == ["plan", "review"]


def test_check_output_is_truncated_to_500_characters(tmp_path, origin, monkeypatch):
    """The `check` event carries only the first 500 characters of the combined output."""
    Fakes(monkeypatch)
    monkeypatch.setattr(engine, "run_command", lambda job, command: (0, "x" * 1234, "", 0.1))
    job_dir = make_job_dir(tmp_path, "long", {"id": "long", "repo": origin, "checks": "[make lint]"})
    assert engine.run(job_dir) == engine.EXIT_OK
    checks = _checks(job_dir)
    assert len(checks) == 1 and len(checks[0]["output"]) == 500


def test_a_job_without_checks_has_no_check_events(tmp_path, origin, monkeypatch):
    """No `checks` key: the push goes straight to `done`, with no `check` events."""
    Fakes(monkeypatch)
    monkeypatch.setattr(engine, "run_command", lambda job, command: pytest.fail("no command should run"))
    job_dir = make_job_dir(tmp_path, "plain", {"id": "plain", "repo": origin})
    assert engine.run(job_dir) == engine.EXIT_OK
    assert _checks(job_dir) == []
    assert any(row["kind"] == "done" for row in _events(job_dir))
