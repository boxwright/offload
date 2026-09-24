"""Tests for `offload add` through `cli.main`: a one-line text, a `--spec` file, and `--confirm`.

`--spec` takes a `job.md`-style file (front matter plus Goal / Done when) and lands the job
`ready` with intake skipped; a plain text lands in the inbox. `--confirm` writes `confirm: true`
on either path. Giving neither a text nor a `--spec` is an error.
"""
import os

from offload import cli, jobs, status
from offload.files import read_text
from offload.jobs import Job

SPEC = """\
---
title: Fix the failing statistics tests in the demo repository
repo: /srv/repos/demo
---
## Goal
The tests in `tests/` fail because of a defect in `calc/__init__.py`. Find and fix it.

## Done when
- `python3 -m pytest -q` passes
"""


def _write_spec(root, text=SPEC):
    path = os.path.join(str(root), "spec.md")
    with open(path, "w") as f:
        f.write(text)
    return path


def _jobs(settings):
    return sorted(os.listdir(settings.jobs_root)) if os.path.isdir(settings.jobs_root) else []


def test_add_with_text_only_lands_in_the_inbox(settings, capsys):
    assert cli.main(["add", "add input validation and tests for it"]) == 0
    (job_id,) = _jobs(settings)
    job_dir = os.path.join(settings.jobs_root, job_id)
    assert status.job_status(job_dir)["status"] == status.INBOX
    job = Job(job_dir)
    assert job.id == job_id
    assert job.title == "add input validation and tests for it"
    assert "add input validation and tests for it" in job.body
    assert job.flag("confirm") is False
    out = capsys.readouterr().out
    assert f"added {job_id}" in out


def test_add_with_spec_lands_ready_and_skips_intake(settings, capsys):
    spec = _write_spec(os.path.dirname(settings.jobs_root))
    assert cli.main(["add", "--spec", spec]) == 0
    (job_id,) = _jobs(settings)
    job_dir = os.path.join(settings.jobs_root, job_id)
    assert status.job_status(job_dir)["status"] == status.READY
    job = Job(job_dir)
    assert job.id == job_id
    assert job.title == "Fix the failing statistics tests in the demo repository"
    assert job.repo == "/srv/repos/demo"
    assert job.branch == f"offload/{job_id}"
    assert job.test_cmd == jobs.DEFAULT_TEST_CMD
    assert "## Goal" in job.body
    assert "## Done when" in job.body
    assert job.flag("confirm") is False
    assert not os.path.exists(job.path("intake.json"))


def test_add_with_spec_and_confirm_writes_confirm_true(settings):
    spec = _write_spec(os.path.dirname(settings.jobs_root))
    assert cli.main(["add", "--spec", spec, "--confirm"]) == 0
    (job_id,) = _jobs(settings)
    job = Job(os.path.join(settings.jobs_root, job_id))
    assert job.flag("confirm") is True
    assert "confirm: true" in read_text(job.path("job.md"))
    assert status.job_status(job.dir)["status"] == status.READY


def test_add_with_text_and_confirm_writes_confirm_true(settings):
    assert cli.main(["add", "a gated one-liner", "--confirm"]) == 0
    (job_id,) = _jobs(settings)
    job = Job(os.path.join(settings.jobs_root, job_id))
    assert job.flag("confirm") is True
    assert "confirm: true" in read_text(job.path("job.md"))
    assert status.job_status(job.dir)["status"] == status.INBOX


def test_add_with_neither_text_nor_spec_is_an_error(settings, capsys):
    assert cli.main(["add"]) == 2
    assert _jobs(settings) == []
    err = capsys.readouterr().err
    assert "--spec" in err
