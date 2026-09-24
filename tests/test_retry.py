"""End-to-end tests for `offload retry`, driven through cli.main the way the owner runs it.

Each test builds a job under the config's jobs root, calls cli.main with the real argv, and checks
the job directory afterwards. No Docker, no network, no real home: the settings fixture points every
file at tmp_path, and the retry path only touches the job directory.
"""
import os

import pytest
from conftest import make_job_dir

from offload import cli, status
from offload.files import write_json, write_text
from offload.jobs import Job
from offload.prompts import step_brief


def _failed_job(jobs_root, name, meta):
    """A job directory under jobs_root, marked failed with a run's leftovers behind it."""
    d = make_job_dir(jobs_root, name, meta)
    status.set_status(d, status.FAILED, reason="boom")
    return d


def test_retry_note_lands_in_the_step_brief(settings):
    """`retry --note` requeues the job and the note reaches the brief the worker is handed."""
    d = _failed_job(settings.jobs_root, "j-note", {"id": "j-note", "repo": "/srv/repos/demo"})
    write_text(os.path.join(d, "progress.json"), '{"phase": "steps", "step": 2}')
    write_text(os.path.join(d, "answer.txt"), "no\n")
    write_text(os.path.join(d, "REPORT.md"), "# old report\n")

    rc = cli.main(["retry", "j-note", "--note", "Use the existing helper, do not add a new one."])
    assert rc == 0

    # requeued, and the run's leftovers are gone
    assert status.job_status(d)["status"] == status.READY
    for name in ("progress.json", "answer.txt", "REPORT.md"):
        assert not os.path.exists(os.path.join(d, name))

    # the note was written, and it is in the brief the worker receives
    assert os.path.exists(os.path.join(d, "note.txt"))
    brief = step_brief(Job(d), "1. write a.txt", "1. write a.txt\n")
    assert "Owner note for this run:" in brief
    assert "Use the existing helper, do not add a new one." in brief


def test_retry_replan_drops_the_plan_but_keeps_the_spec(settings):
    """`retry --replan` makes the plan again but reuses the spec, so intake is skipped."""
    d = _failed_job(settings.jobs_root, "j-replan", {"id": "j-replan", "repo": "/srv/repos/demo"})
    write_text(os.path.join(d, "plan.txt"), "1. write a.txt\n2. write b.txt\n")
    write_text(os.path.join(d, "plan.md"), "# Plan — j-replan\n\n1. write a.txt\n2. write b.txt\n")
    write_json(os.path.join(d, "intake.json"), {"repo": "/srv/repos/demo", "title": "j-replan"})

    rc = cli.main(["retry", "j-replan", "--replan"])
    assert rc == 0

    # the stored plan is gone, so the planner runs again
    assert not os.path.exists(os.path.join(d, "plan.txt"))
    assert not os.path.exists(os.path.join(d, "plan.md"))
    # the spec and the intake record are kept, so the daemon runs the job instead of intake
    assert os.path.exists(os.path.join(d, "job.md"))
    assert os.path.exists(os.path.join(d, "intake.json"))
    assert Job(d).repo == "/srv/repos/demo"
    assert status.job_status(d)["status"] == status.READY


def test_retry_without_replan_keeps_the_stored_plan(settings):
    """A plain `retry` reuses the stored plan: it is not dropped."""
    d = _failed_job(settings.jobs_root, "j-keep", {"id": "j-keep", "repo": "/srv/repos/demo"})
    write_text(os.path.join(d, "plan.txt"), "1. write a.txt\n2. write b.txt\n")
    write_text(os.path.join(d, "plan.md"), "# Plan — j-keep\n\n1. write a.txt\n2. write b.txt\n")

    rc = cli.main(["retry", "j-keep"])
    assert rc == 0

    assert os.path.exists(os.path.join(d, "plan.txt"))
    assert os.path.exists(os.path.join(d, "plan.md"))
    assert status.job_status(d)["status"] == status.READY


@pytest.mark.parametrize("state", [status.RUNNING, status.DONE])
def test_retry_refuses_a_job_that_is_not_failed(settings, state, capsys):
    """Retrying a running or done job is refused, the state is named, and nothing changes."""
    d = make_job_dir(settings.jobs_root, "j-busy", {"id": "j-busy", "repo": "/srv/repos/demo"})
    status.set_status(d, state)
    write_text(os.path.join(d, "progress.json"), '{"phase": "steps", "step": 2}')

    rc = cli.main(["retry", "j-busy"])
    assert rc != 0
    assert state in capsys.readouterr().out
    # refused: the state and the run's files are untouched
    assert status.job_status(d)["status"] == state
    assert os.path.exists(os.path.join(d, "progress.json"))
