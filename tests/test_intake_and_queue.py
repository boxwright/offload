"""Tests for the pure parts of intake, the job listing, the queue order, and the restart requeue."""
import json
import os

import pytest
from conftest import make_job_dir

from offload import daemon, files, intake, jobs, notify, status


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


def test_finished_jobs_are_not_offered_again_until_their_status_file_changes(tmp_path):
    done = make_job_dir(tmp_path, "a")
    status.set_status(done, status.FAILED)
    daemon._finished.clear()
    assert daemon._next_job(tmp_path) is None
    assert done in daemon._finished
    jobs.retry(done)                      # rewrites status.json: the daemon must see the job again
    assert daemon._next_job(tmp_path) == (status.READY, done)
    assert done not in daemon._finished


def test_intake_writes_no_tier_key(tmp_path):
    job_dir = make_job_dir(tmp_path, "t")
    intake._write_job_file(jobs.Job(job_dir), {"repo": "/r.git", "title": "T", "goal": "g", "done_when": "a | b"})
    text = (tmp_path / "t" / "job.md").read_text()
    assert "tier" not in text and "repo: /r.git" in text and "- a\n- b" in text


def test_intake_posts_the_drafted_spec_and_leaves_the_job_ready(tmp_path, monkeypatch):
    job_dir = make_job_dir(tmp_path, "a-draft", {"id": "a-draft"})
    status.set_status(job_dir, status.INBOX)

    reply = ("Here is the spec:\n```yaml\ntitle: Add a thing\nrepo: /r.git\n"
             "goal: Do the thing\ndone_when: criterion one|criterion two\n```\n")
    monkeypatch.setattr(intake, "claude", lambda *a, **k: (reply, {}))

    posted = []

    def fake_post(text):
        posted.append(text)
        return True, 200
    monkeypatch.setattr(notify, "post", fake_post)

    assert intake.intake(job_dir) is True

    assert len(posted) == 1
    message = posted[0]
    assert "Add a thing" in message
    assert "Do the thing" in message
    assert "criterion one" in message
    assert "criterion two" in message

    record = status.job_status(job_dir)
    assert record["status"] == status.READY
    assert record.get("gate") is None
    assert record.get("deadline") is None


def test_repo_add_verifies_then_writes_a_quoted_line_and_list_reads_it(settings, tmp_path, capsys, monkeypatch):
    from offload import repos
    monkeypatch.setattr(repos, "sh", lambda cmd, **kw: (0, "abc\trefs/heads/main\n", "", 0.1))
    assert repos.add("/srv/git/x.git", "Netwatch: scanners, monitors; tests are unittest") == 0
    assert repos.known_repos() == {"/srv/git/x.git": "Netwatch: scanners, monitors; tests are unittest"}
    assert repos.add("/srv/git/x.git", "again") == 0 and len(repos.known_repos()) == 1
    assert repos.add("/srv/git/../git/x.git", "same repository, other spelling") == 0
    assert len(repos.known_repos()) == 1
    monkeypatch.setattr(repos, "sh", lambda cmd, **kw: (128, "", "fatal: not a git repository", 0.1))
    assert repos.add("/nowhere", "x") == 1
    repos.list_repos()
    assert "/srv/git/x.git: Netwatch" in capsys.readouterr().out


def test_a_bad_repos_file_names_the_line_and_intake_asks_the_owner(settings, tmp_path, monkeypatch):
    from offload import repos
    (tmp_path / "repos.yaml").write_text("/a.git: fine\n/b.git: Netwatch: home monitoring\n")
    with pytest.raises(ValueError) as err:
        repos.known_repos()
    assert "line 2" in str(err.value) and "repos.yaml" in str(err.value)
    job_dir = make_job_dir(tmp_path / "jobs", "q", body="## Goal\nfix the thing\n")
    monkeypatch.setattr(intake, "claude", lambda *a, **k: ("```yaml\ntitle: T\nrepo: UNKNOWN\n```", {}))
    asked = []
    monkeypatch.setattr(intake.notify, "ask_owner", lambda job, gate, q: asked.append(gate) or "/a.git")
    assert intake.intake(job_dir) is True
    assert asked == ["intake"]
    kinds = [row["kind"] for row in files.read_jsonl(os.path.join(job_dir, "events.jsonl"))]
    assert "repos_unreadable" in kinds


def test_report_on_an_unfinished_job_is_one_line_not_a_traceback(settings, tmp_path, capsys):
    from offload.cli import main
    job_dir = make_job_dir(tmp_path / "jobs", "r")
    status.set_status(job_dir, status.RUNNING)
    assert main(["report", job_dir]) == 1
    assert "no report yet: the job is running" in capsys.readouterr().out
