"""Parking and resume: a waiting job gives the loop back, and a job that goes again skips what is finished."""
import os
import subprocess
import time

import pytest
from conftest import make_job_dir

from offload import budget, daemon, engine, jobs, notify, progress, sandbox, status, workers
from offload.clock import iso_after
from offload.jobs import Job

PLAN_TEXT = "1. write a.txt\n2. write b.txt\n3. write c.txt\n"


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    """No webhook post, and the ledger and the budget file live in tmp_path."""
    monkeypatch.setattr(notify, "post_webhook", lambda text: (False, "test"))
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

    def claude(self, job, prompt, model, max_turns, purpose):
        self.claude_purposes.append(purpose)
        return (PLAN_TEXT if purpose == "plan" else "APPROVE"), {}

    def local(self, job, brief, purpose):
        self.local_purposes.append(purpose)
        name = brief.split()[-1]
        with open(os.path.join(job.work, name), "w") as f:
            f.write(purpose)
        return "done", {"worker": "fake", "wall_s": 0}


def test_a_gate_parks_the_job_and_the_loop_takes_the_next_one(tmp_path, job_factory):
    gated = job_factory("a-gated", {"id": "a-gated", "repo": "/r.git"})
    plain = job_factory("b-plain", {"id": "b-plain", "repo": "/r.git"})
    with pytest.raises(status.Parked) as parked:
        notify.ask_owner(Job(gated), "publish", "Push?")
    daemon._park(gated, parked.value)
    record = status.job_status(gated)
    assert record["status"] == status.WAITING_OWNER and record["gate"] == "publish"
    assert daemon._next_job(tmp_path) == (status.READY, plain)


def test_an_answer_wakes_the_parked_job_ahead_of_newer_work(tmp_path, job_factory):
    gated = job_factory("a-gated", {"id": "a-gated", "repo": "/r.git"})
    job_factory("b-plain", {"id": "b-plain", "repo": "/r.git"})
    with pytest.raises(status.Parked) as parked:
        notify.ask_owner(Job(gated), "publish", "Push?")
    daemon._park(gated, parked.value)
    (tmp_path / "a-gated" / "answer.txt").write_text("yes\n")
    assert daemon._next_job(tmp_path) == (status.WAITING_OWNER, gated)
    assert notify.ask_owner(Job(gated), "publish", "Push?") == "yes"
    assert not (tmp_path / "a-gated" / "answer.txt").exists()
    assert (tmp_path / "a-gated" / "answer-publish.txt").exists()
    assert status.job_status(gated)["gate"] is None


def test_a_gate_past_its_deadline_wakes_and_returns_none(tmp_path, job_factory):
    gated = job_factory("a-gated", {"id": "a-gated", "repo": "/r.git"})
    status.set_status(gated, status.WAITING_OWNER, gate="publish", deadline=time.time() - 1)
    assert daemon._next_job(tmp_path) == (status.WAITING_OWNER, gated)
    assert notify.ask_owner(Job(gated), "publish", "Push?") is None


def test_an_old_answer_does_not_answer_a_new_gate(job_factory):
    gated = job_factory("a-gated", {"id": "a-gated", "repo": "/r.git"})
    with open(os.path.join(gated, "answer.txt"), "w") as f:
        f.write("yes\n")
    with pytest.raises(status.Parked):
        notify.ask_owner(Job(gated), "publish", "Push?")
    assert not os.path.exists(os.path.join(gated, "answer.txt"))


@pytest.mark.parametrize("state", [status.WAITING_LIMIT, status.WAITING_BUDGET])
def test_a_timed_park_is_skipped_until_its_time(tmp_path, job_factory, state):
    parked = job_factory("a-parked", {"id": "a-parked", "repo": "/r.git"})
    status.set_status(parked, state, until=iso_after(3600))
    assert daemon._next_job(tmp_path) is None
    status.set_status(parked, state, until=iso_after(-1))
    assert daemon._next_job(tmp_path) == (state, parked)


def test_the_loop_parks_a_job_that_raises_parked(tmp_path, job_factory, monkeypatch):
    job_dir = job_factory("a", {"id": "a", "repo": "/r.git"})

    def parks(_job_dir):
        raise status.Parked(status.WAITING_LIMIT, until=iso_after(60))
    monkeypatch.setattr(daemon, "run", parks)
    daemon._run_and_report(job_dir)
    assert status.job_status(job_dir)["status"] == status.WAITING_LIMIT
    assert not os.path.exists(os.path.join(job_dir, "REPORT.md"))


def test_a_full_job_writes_its_checkpoint_and_pushes(tmp_path, origin, monkeypatch):
    fakes = Fakes(monkeypatch)
    job_dir = make_job_dir(tmp_path, "full", {"id": "full", "repo": origin})
    assert engine.run(job_dir) == engine.EXIT_OK
    assert fakes.claude_purposes == ["plan", "review"]
    assert fakes.local_purposes == ["step 1", "step 2", "step 3"]
    assert progress.load(Job(job_dir))["phase"] == progress.PUSH
    branches = subprocess.run(["git", "branch", "--list"], cwd=origin, capture_output=True, text=True).stdout
    assert "offload/full" in branches


def test_a_job_that_stopped_in_step_two_continues_there_and_does_not_plan_again(tmp_path, origin, monkeypatch):
    fakes = Fakes(monkeypatch)
    job_dir = make_job_dir(tmp_path, "cut", {"id": "cut", "repo": origin})
    calls = {"n": 0}

    def dies_in_step_two(job, brief, purpose):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt
        return fakes.local(job, brief, purpose)
    monkeypatch.setattr(engine, "local_harness", dies_in_step_two)
    with pytest.raises(KeyboardInterrupt):
        engine.run(job_dir)
    assert progress.load(Job(job_dir))["step"] == 2

    monkeypatch.setattr(engine, "local_harness", fakes.local)
    assert engine.run(job_dir) == engine.EXIT_OK
    assert fakes.claude_purposes == ["plan", "review"]
    assert fakes.local_purposes == ["step 1", "step 2", "step 3"]


def test_a_public_job_parks_at_the_gate_and_pushes_after_a_yes(tmp_path, origin, monkeypatch):
    fakes = Fakes(monkeypatch)
    jobs_root = tmp_path / "jobs"
    job_dir = make_job_dir(jobs_root, "pub", {"id": "pub", "repo": origin, "public": "true"})
    daemon._run_and_report(job_dir)
    assert status.job_status(job_dir)["status"] == status.WAITING_OWNER
    assert progress.load(Job(job_dir))["phase"] == progress.GATE
    assert daemon._next_job(jobs_root) is None

    (jobs_root / "pub" / "answer.txt").write_text("yes\n")
    assert daemon._next_job(jobs_root) == (status.WAITING_OWNER, job_dir)
    daemon._run_and_report(job_dir)
    assert status.job_status(job_dir)["status"] == status.DONE
    assert fakes.claude_purposes == ["plan", "review"]
    assert len(fakes.local_purposes) == 3


def test_claude_makes_no_call_while_the_account_is_blocked(tmp_path, job_factory, monkeypatch):
    monkeypatch.setattr(workers, "_blocked_until_file", lambda: str(tmp_path / "claude-blocked-until"))
    monkeypatch.setattr(workers, "_call_claude", lambda *args, **kwargs: pytest.fail("a call was made"))
    (tmp_path / "claude-blocked-until").write_text(iso_after(600) + "\n")
    with pytest.raises(status.Parked) as parked:
        workers.claude(Job(job_factory()), "prompt", "sonnet", 2, "review")
    assert parked.value.status == status.WAITING_LIMIT


def test_a_limit_parks_the_job_and_the_next_call_resumes_that_session(tmp_path, job_factory, monkeypatch):
    monkeypatch.setattr(workers, "_blocked_until_file", lambda: str(tmp_path / "claude-blocked-until"))
    monkeypatch.setattr(workers, "budget_wait", lambda job, purpose: None)
    monkeypatch.setattr(workers, "ledger_add", lambda *args, **kwargs: None)
    job = Job(job_factory())
    limit_reply = {"is_error": True, "result": "You've hit your session limit · resets in 5 minutes",
                   "session_id": "sess-1"}
    monkeypatch.setattr(workers, "_call_claude", lambda *args, **kwargs: (limit_reply, 1.0))
    with pytest.raises(status.Parked):
        workers.claude(job, "prompt", "sonnet", 2, "review")
    assert progress.pending_session(job, "review") == "sess-1"
    assert progress.pending_session(job, "plan") is None

    resumed = []

    def call(job, prompt, model, max_turns, resume=None):
        resumed.append(resume)
        return {"result": "APPROVE", "session_id": "sess-1"}, 1.0
    monkeypatch.setattr(workers, "_call_claude", call)
    (tmp_path / "claude-blocked-until").write_text(iso_after(-1) + "\n")
    text, _ = workers.claude(job, "prompt", "sonnet", 2, "review")
    assert text == "APPROVE" and resumed == ["sess-1"]
    assert progress.pending_session(job, "review") is None


def test_the_pacer_parks_a_job_when_the_week_is_ahead_of_pace(job_factory, monkeypatch):
    pace = budget.Pace(allowed=False, spent=50.0, pace_now=10.0, allowance=90.0, wait_s=1200)
    monkeypatch.setattr(budget, "pace_status", lambda _budget: pace)
    monkeypatch.setattr(budget, "load_budget", lambda: {})
    with pytest.raises(status.Parked) as parked:
        budget.budget_wait(Job(job_factory()), "plan")
    assert parked.value.status == status.WAITING_BUDGET and parked.value.wake["wait_s"] == 1200


def test_leftover_worker_containers_are_killed_by_label(monkeypatch):
    commands = []

    def fake_sh(cmd, **kwargs):
        commands.append(cmd)
        return 0, "abc123\ndef456\n" if "ps" in cmd else "", "", 0.0
    monkeypatch.setattr(sandbox, "sh", fake_sh)
    monkeypatch.setattr(sandbox, "_with_docker_group", lambda cmd: cmd)
    assert sandbox.kill_leftover_containers() == 2
    assert commands[0] == ["docker", "ps", "-q", "--filter", "label=offload.role=worker"]
    assert commands[1] == ["docker", "kill", "abc123", "def456"]


def test_cancel_fails_a_parked_job_at_once(tmp_path, job_factory):
    parked = job_factory("a", {"id": "a", "repo": "/r.git"})
    status.set_status(parked, status.WAITING_OWNER, gate="publish", deadline=time.time() + 60)
    jobs.cancel(parked)
    assert status.job_status(parked)["status"] == status.FAILED
    assert daemon._next_job(tmp_path) is None


def test_a_cancelled_running_job_stops_before_its_next_worker_call(tmp_path, origin, monkeypatch):
    fakes = Fakes(monkeypatch)
    job_dir = make_job_dir(tmp_path / "jobs", "c", {"id": "c", "repo": origin})

    def cancels_after_step_one(job, brief, purpose):
        result = fakes.local(job, brief, purpose)
        with open(job.path("cancel"), "w") as f:
            f.write("now\n")
        return result
    monkeypatch.setattr(engine, "local_harness", cancels_after_step_one)
    assert engine.run(job_dir) == engine.EXIT_CANCELLED
    assert fakes.local_purposes == ["step 1"]
    assert fakes.claude_purposes == ["plan"]


def test_every_worker_container_is_capped(settings, monkeypatch):
    commands = []

    def fake_sh(cmd, **kwargs):
        commands.append(cmd)
        return 0, "", "", 0.0
    monkeypatch.setattr(sandbox, "sh", fake_sh)
    monkeypatch.setattr(sandbox, "_with_docker_group", lambda cmd: cmd)
    sandbox.run_shell_in_sandbox("true", "/tmp/work")
    cmd = commands[0]
    for flag, value in (("--memory", "4g"), ("--memory-swap", "4g"), ("--cpus", "2.0"), ("--pids-limit", "512"),
                        ("--security-opt", "no-new-privileges")):
        assert cmd[cmd.index(flag) + 1] == value
