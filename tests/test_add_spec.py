"""Tests for `jobs.add` with a `job.md`-style spec file and the `confirm` flag.

A spec file skips intake (the job lands `ready` with its front matter filled in); a one-line
`text` still lands in the inbox. `confirm=True` writes `confirm: true` into the front matter
on both paths.
"""
import os

from offload import jobs, status
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
- the change touches only `calc/`
"""


def _write_spec(root, text=SPEC):
    path = os.path.join(str(root), "spec.md")
    with open(path, "w") as f:
        f.write(text)
    return path


def test_a_spec_file_lands_ready_with_id_branch_and_test_filled(tmp_path):
    spec = _write_spec(tmp_path)
    job_id = jobs.add(str(tmp_path), "", spec_file=spec)
    job_dir = os.path.join(str(tmp_path), job_id)
    assert status.job_status(job_dir)["status"] == status.READY

    job = Job(job_dir)
    assert job.id == job_id
    assert job.title == "Fix the failing statistics tests in the demo repository"
    assert job.repo == "/srv/repos/demo"
    assert job.branch == f"offload/{job_id}"
    assert job.test_cmd == jobs.DEFAULT_TEST_CMD
    assert "## Goal" in job.body
    assert "The tests in `tests/` fail" in job.body
    assert "## Done when" in job.body
    assert "- the change touches only `calc/`" in job.body
    # intake's Claude call is skipped: no draft is asked for or kept
    assert not os.path.exists(job.path("intake.json"))


def test_a_spec_file_keeps_its_own_branch_and_test(tmp_path):
    spec = _write_spec(tmp_path, """\
---
title: A custom job
repo: /srv/repos/demo
branch: offload/custom-branch
test: python3 -m pytest -q tests
---
## Goal
Do the thing.
""")
    job_id = jobs.add(str(tmp_path), "", spec_file=spec)
    job = Job(os.path.join(str(tmp_path), job_id))
    assert job.branch == "offload/custom-branch"
    assert job.test_cmd == "python3 -m pytest -q tests"


def test_confirm_on_a_spec_file_writes_confirm_true(tmp_path):
    spec = _write_spec(tmp_path)
    job_id = jobs.add(str(tmp_path), "", spec_file=spec, confirm=True)
    job = Job(os.path.join(str(tmp_path), job_id))
    assert job.flag("confirm") is True
    assert "confirm: true" in read_text(job.path("job.md"))
    assert status.job_status(job.dir)["status"] == status.READY


def test_a_spec_file_without_front_matter_is_taken_as_the_body(tmp_path):
    spec = _write_spec(tmp_path, "## Goal\nJust a goal, no front matter.\n")
    job_id = jobs.add(str(tmp_path), "", spec_file=spec)
    job = Job(os.path.join(str(tmp_path), job_id))
    assert job.id == job_id
    assert job.branch == f"offload/{job_id}"
    assert job.test_cmd == jobs.DEFAULT_TEST_CMD
    assert "Just a goal, no front matter." in job.body
    assert status.job_status(job.dir)["status"] == status.READY


def test_a_one_line_text_still_lands_in_the_inbox(tmp_path):
    job_id = jobs.add(str(tmp_path), "add input validation and tests for it")
    job_dir = os.path.join(str(tmp_path), job_id)
    assert status.job_status(job_dir)["status"] == status.INBOX
    job = Job(job_dir)
    assert job.id == job_id
    assert job.title == "add input validation and tests for it"
    assert "## Goal" in job.body
    assert "add input validation and tests for it" in job.body


def test_confirm_on_a_one_line_text_writes_confirm_true(tmp_path):
    job_id = jobs.add(str(tmp_path), "a gated one-liner", confirm=True)
    job = Job(os.path.join(str(tmp_path), job_id))
    assert job.flag("confirm") is True
    assert "confirm: true" in read_text(job.path("job.md"))
    assert status.job_status(job.dir)["status"] == status.INBOX


def test_no_confirm_flag_writes_no_confirm_key(tmp_path):
    spec = _write_spec(tmp_path)
    job_id = jobs.add(str(tmp_path), "", spec_file=spec)
    assert Job(os.path.join(str(tmp_path), job_id)).flag("confirm") is False

    text_id = jobs.add(str(tmp_path), "plain")
    assert Job(os.path.join(str(tmp_path), text_id)).flag("confirm") is False
