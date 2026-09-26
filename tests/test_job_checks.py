"""Tests for the optional `checks` front-matter key on a Job, and the daemon guard that fails an
unparseable job.md instead of taking the loop down.

Job dirs are built under tmp_path, so no test touches the network, Docker, or the real home directory.
"""
import os

import pytest

from offload import daemon, jobs, status


def _write_job(root, name, front_matter, body="## Goal\nDo the thing\n"):
    """A job dir whose job.md carries the exact front-matter text given (so block lists can be tested)."""
    job_dir = os.path.join(os.fspath(root), name)
    os.makedirs(job_dir, exist_ok=True)
    with open(os.path.join(job_dir, "job.md"), "w") as f:
        f.write(f"---\n{front_matter}\n---\n{body}")
    return job_dir


# ---------------------------------------------------------------- checks: present
def test_checks_absent_defaults_to_empty_list(tmp_path):
    """A job.md with no checks key parses to Job.checks == []."""
    d = _write_job(tmp_path, "j-c0", "id: j-c0\nrepo: /srv/repos/demo")
    assert jobs.Job(d).checks == []


def test_checks_inline_list(tmp_path):
    """An inline bracketed checks list is parsed into Job.checks."""
    d = _write_job(tmp_path, "j-c1", "id: j-c1\nrepo: /srv/repos/demo\nchecks: [make lint, make test]")
    assert jobs.Job(d).checks == ["make lint", "make test"]


def test_checks_inline_single_item(tmp_path):
    """A single inline check parses to a one-element list."""
    d = _write_job(tmp_path, "j-c2", "id: j-c2\nrepo: /srv/repos/demo\nchecks: [make lint]")
    assert jobs.Job(d).checks == ["make lint"]


def test_checks_inline_empty_brackets(tmp_path):
    """An empty inline list parses to []."""
    d = _write_job(tmp_path, "j-c3", "id: j-c3\nrepo: /srv/repos/demo\nchecks: []")
    assert jobs.Job(d).checks == []


def test_checks_block_list(tmp_path):
    """Indented `- ` block lines under a bare checks: are parsed into Job.checks."""
    fm = "id: j-c4\nrepo: /srv/repos/demo\nchecks:\n  - make lint\n  - make test"
    d = _write_job(tmp_path, "j-c4", fm)
    assert jobs.Job(d).checks == ["make lint", "make test"]


def test_checks_block_list_stops_at_next_key(tmp_path):
    """Block lines are collected only until the next top-level key."""
    fm = "id: j-c5\nrepo: /srv/repos/demo\nchecks:\n  - make lint\ntest: python3 -m pytest -q"
    d = _write_job(tmp_path, "j-c5", fm)
    job = jobs.Job(d)
    assert job.checks == ["make lint"]
    assert job.test_cmd == "python3 -m pytest -q"


def test_checks_quotes_are_stripped(tmp_path):
    """Surrounding quotes on inline and block items are removed."""
    d = _write_job(tmp_path, "j-c6", 'id: j-c6\nrepo: /srv/repos/demo\nchecks: ["make lint", \'make test\']')
    assert jobs.Job(d).checks == ["make lint", "make test"]


# ---------------------------------------------------------------- checks: malformed
def test_checks_malformed_scalar_raises_naming_checks(tmp_path):
    """A bare scalar (not a list) raises a JobError whose message names checks."""
    d = _write_job(tmp_path, "j-c7", "id: j-c7\nrepo: /srv/repos/demo\nchecks: make lint")
    with pytest.raises(jobs.JobError) as excinfo:
        jobs.Job(d)
    assert "checks" in str(excinfo.value)


def test_checks_malformed_unbalanced_brackets_raises(tmp_path):
    """An unbalanced inline list raises a JobError whose message names checks."""
    d = _write_job(tmp_path, "j-c8", "id: j-c8\nrepo: /srv/repos/demo\nchecks: [make lint")
    with pytest.raises(jobs.JobError) as excinfo:
        jobs.Job(d)
    assert "checks" in str(excinfo.value)


def test_checks_malformed_empty_item_raises(tmp_path):
    """An empty entry in the list raises a JobError whose message names checks."""
    d = _write_job(tmp_path, "j-c9", "id: j-c9\nrepo: /srv/repos/demo\nchecks: [make lint, ]")
    with pytest.raises(jobs.JobError) as excinfo:
        jobs.Job(d)
    assert "checks" in str(excinfo.value)


def test_checks_job_error_is_an_exception():
    """JobError is a plain exception the daemon can catch without importing engine specifics."""
    assert issubclass(jobs.JobError, Exception)


# ---------------------------------------------------------------- daemon guard
def test_job_or_fail_returns_job_for_a_parsable_job_md(settings, tmp_path):
    """A valid job.md yields a Job and leaves the status untouched (not failed)."""
    d = _write_job(tmp_path, "j-d0", "id: j-d0\nrepo: /srv/repos/demo\nchecks: [make lint]")
    job = daemon._job_or_fail(d)
    assert job is not None
    assert job.checks == ["make lint"]
    assert status.job_status(d).get("status") != status.FAILED


def test_job_or_fail_fails_the_job_on_an_unparsable_job_md(settings, tmp_path):
    """An unparseable job.md (bad checks) fails the job and returns None, instead of raising."""
    d = _write_job(tmp_path, "j-d1", "id: j-d1\nrepo: /srv/repos/demo\nchecks: make lint")
    assert daemon._job_or_fail(d) is None
    record = status.job_status(d)
    assert record["status"] == status.FAILED
    assert "checks" in record.get("reason", "")


def test_fail_event_tolerates_an_unparsable_job_md(settings, tmp_path):
    """_fail_event records a fail event for a good job and does not raise for a bad one."""
    good = _write_job(tmp_path, "j-d2", "id: j-d2\nrepo: /srv/repos/demo")
    daemon._fail_event(good, "boom")
    with open(os.path.join(good, "events.jsonl")) as f:
        assert "fail" in f.read()
    bad = _write_job(tmp_path, "j-d3", "id: j-d3\nrepo: /srv/repos/demo\nchecks: make lint")
    daemon._fail_event(bad, "boom")  # must not raise
