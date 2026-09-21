"""Tests for the pure parts of intake, the job listing, the queue order, and the restart requeue."""
import json
import os

from conftest import make_job_dir

from offload import daemon, files, intake, jobs, status


def test_extract_yaml_from_a_fenced_block():
    reply = "Here you go:\n```yaml\ntitle: Add a thing\nrepo: /r.git\n```\nthanks"
    assert intake.extract_yaml(reply) == {"title": "Add a thing", "repo": "/r.git"}


def test_extract_yaml_skips_leading_prose():
    assert intake.extract_yaml("Sure.\ntitle: T\nrepo: UNKNOWN\n") == {"title": "T", "repo": "UNKNOWN"}


def test_extract_yaml_rejects_non_mappings():
    assert intake.extract_yaml("just a sentence") is None
    assert intake.extract_yaml("```\n- a\n- b\n```") is None


def test_job_dirs_sorted_and_templates_hidden(tmp_path):
    for name in ("b-job", "a-job", "_templates"):
        os.makedirs(tmp_path / name)
    (tmp_path / "a-file").write_text("not a job")
    assert [os.path.basename(d) for d in jobs.job_dirs(tmp_path)] == ["a-job", "b-job"]
    assert len(jobs.job_dirs(tmp_path, include_hidden=True)) == 3


def test_next_job_prefers_inbox_then_ready(tmp_path):
    ready = make_job_dir(tmp_path, "a-ready")
    inbox = make_job_dir(tmp_path, "b-inbox")
    done = make_job_dir(tmp_path, "c-done")
    status.set_status(ready, status.READY)
    status.set_status(inbox, status.INBOX)
    status.set_status(done, status.DONE)
    assert daemon._next_job(tmp_path) == (status.INBOX, inbox)
    status.set_status(inbox, status.DONE)
    assert daemon._next_job(tmp_path) == (status.READY, ready)
    status.set_status(ready, status.DONE)
    assert daemon._next_job(tmp_path) is None


def test_restart_requeues_a_running_job_and_leaves_parked_jobs_parked(tmp_path):
    states = {"run": status.RUNNING, "lim": status.WAITING_LIMIT, "own": status.WAITING_OWNER,
              "bud": status.WAITING_BUDGET, "fin": status.DONE, "bad": status.FAILED}
    dirs = {name: make_job_dir(tmp_path, name) for name in states}
    for name, state in states.items():
        status.set_status(dirs[name], state)
    daemon._requeue_interrupted(tmp_path)
    after = {name: status.job_status(job_dir)["status"] for name, job_dir in dirs.items()}
    assert after == {"run": "ready", "lim": "waiting_limit", "own": "waiting_owner", "bud": "waiting_budget",
                     "fin": "done", "bad": "failed"}
    assert status.job_status(dirs["run"])["restarted"] == 1


def test_corrupt_status_file_fails_the_job_instead_of_rerunning_it(tmp_path):
    job_dir = make_job_dir(tmp_path, "j")
    (tmp_path / "j" / "status.json").write_text("{not json")
    assert status.job_status(job_dir)["status"] == status.FAILED


def test_write_json_is_atomic_and_read_jsonl_tolerates_a_missing_file(tmp_path):
    path = tmp_path / "x.json"
    files.write_json(path, {"a": 1})
    assert json.loads(path.read_text()) == {"a": 1}
    assert not (tmp_path / "x.json.tmp").exists()
    assert list(files.read_jsonl(tmp_path / "missing.jsonl")) == []


def test_extract_yaml_survives_prose_with_a_colon():
    reply = "Sure: here is the job file you asked for:\ntitle: T\nrepo: /r.git\n"
    assert intake.extract_yaml(reply) == {"title": "T", "repo": "/r.git"}


def test_add_twice_in_one_second_gets_two_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs.time, "strftime", lambda fmt: "j20260101-000000")
    first = jobs.add(str(tmp_path), "one")
    second = jobs.add(str(tmp_path), "two")
    assert first == "j20260101-000000" and second == "j20260101-000000-2"


def test_finished_jobs_are_not_offered_again(tmp_path):
    done = make_job_dir(tmp_path, "a")
    status.set_status(done, status.DONE)
    daemon._finished.clear()
    assert daemon._next_job(tmp_path) is None
    assert done in daemon._finished
