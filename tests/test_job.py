"""Tests for the engine's job model: Job front-matter parsing, job_status /
set_status persistence, and the is_stuck marker.

Job dirs are built under tmp_path via the job_factory fixture, and
set_status / job_status only touch the job dir itself, so no test writes
outside tmp_path or touches the network or Docker.
"""
import json
import os

from offload.prompts import step_brief


# ---------------------------------------------------------------- Job parsing
def test_job_parses_front_matter_keys(api, job_factory):
    """id / repo / branch / test keys from the front matter land on the Job."""
    d = job_factory(name="j-100", meta={
        "id": "j-100",
        "repo": "/srv/repos/demo",
        "branch": "offload/j-100-custom",
        "test": "python3 -m pytest -q tests",
    })
    job = api.Job(d)
    assert job.id == "j-100"
    assert job.repo == "/srv/repos/demo"
    assert job.branch == "offload/j-100-custom"
    assert job.test_cmd == "python3 -m pytest -q tests"
    assert job.meta == {"id": "j-100", "repo": "/srv/repos/demo",
                        "branch": "offload/j-100-custom", "test": "python3 -m pytest -q tests"}


def test_job_default_test_cmd(api, job_factory):
    """A job without a test key uses the default `python3 -m pytest -q`."""
    d = job_factory(name="j-101", meta={"id": "j-101", "repo": "/srv/repos/demo"})
    job = api.Job(d)
    assert job.test_cmd == "python3 -m pytest -q"


def test_job_default_branch_from_id(api, job_factory):
    """A job without a branch key defaults to `engine/<id>`."""
    d = job_factory(name="j-102", meta={"id": "j-102", "repo": "/srv/repos/demo"})
    job = api.Job(d)
    assert job.branch == "offload/j-102"


def test_job_inbox_job_without_repo(api, job_factory):
    """An inbox job (no repo key) parses with an empty repo string."""
    d = job_factory(name="j-103", meta={"id": "j-103", "title": "a one-liner"})
    job = api.Job(d)
    assert job.id == "j-103"
    assert job.repo == ""
    # the body is everything after the front matter
    assert "## Goal" in job.body


def test_job_id_falls_back_to_dir_name(api, job_factory):
    """A job.md without an id key takes the directory name as its id."""
    d = job_factory(name="j-104", meta={"repo": "/srv/repos/demo"})
    job = api.Job(d)
    assert job.id == "j-104"
    assert job.branch == "offload/j-104"


# ---------------------------------------------------------------- status
def test_job_status_defaults_to_ready_when_job_md_exists(api, job_factory):
    """No status.json but a job.md present -> status defaults to 'ready'."""
    d = job_factory(name="j-105", meta={"id": "j-105", "repo": "/srv/repos/demo"})
    assert not os.path.exists(os.path.join(d, "status.json"))
    assert api.job_status(d) == {"status": "ready"}


def test_job_status_defaults_to_inbox_without_job_md(api, tmp_path):
    """An empty dir (no job.md, no status.json) -> status defaults to 'inbox'."""
    d = tmp_path / "j-106"
    d.mkdir()
    assert api.job_status(str(d)) == {"status": "inbox"}


def test_set_status_persists_fields(api, job_factory):
    """set_status writes status.json; job_status reads the fields back."""
    d = job_factory(name="j-107", meta={"id": "j-107", "repo": "/srv/repos/demo"})
    cur = api.set_status(d, "waiting_budget", wait_s=1200, reason="pace")
    assert cur["status"] == "waiting_budget"
    sf = os.path.join(d, "status.json")
    assert os.path.exists(sf)
    with open(sf) as f:
        on_disk = json.load(f)
    assert on_disk["status"] == "waiting_budget"
    assert on_disk["wait_s"] == 1200
    assert on_disk["reason"] == "pace"
    assert "updated" in on_disk
    # and job_status now sees the persisted state, not the default
    assert api.job_status(d) == on_disk


def test_set_status_merges_previous_fields(api, job_factory):
    """A second set_status keeps fields from the first and updates the rest."""
    d = job_factory(name="j-108", meta={"id": "j-108", "repo": "/srv/repos/demo"})
    api.set_status(d, "running", started="2026-09-17 10:00:00")
    api.set_status(d, "done", rc=0)
    st = api.job_status(d)
    assert st["status"] == "done"
    assert st["rc"] == 0
    assert st["started"] == "2026-09-17 10:00:00"  # carried over, not dropped


# ---------------------------------------------------------------- is_stuck
def test_is_stuck_stuck_with_reason(api):
    """A final answer starting with 'STUCK — reason' counts as stuck."""
    assert api.is_stuck("STUCK — the sandbox image is missing and I cannot build it") is True


def test_is_stuck_stuck_no_is_not_stuck(api):
    """'STUCK: no — done' is an explicit non-stuck declaration."""
    assert api.is_stuck("STUCK: no — done") is False


def test_is_stuck_word_mid_sentence_is_not_stuck(api):
    """The word STUCK mid-sentence (not at line start) is not a stuck marker."""
    assert api.is_stuck("I am STUCK on this step but will keep trying") is False


def test_is_stuck_marker_on_its_own_line(api):
    """A STUCK marker on its own line, after other text, still counts."""
    assert api.is_stuck("Worked for a while.\nSTUCK — no way to install the dependency") is True


# ---------------------------------------------------------------- note
def test_job_note_empty_when_no_note_file(api, job_factory):
    """A job without note.txt has an empty note."""
    d = job_factory(name="j-109", meta={"id": "j-109", "repo": "/srv/repos/demo"})
    assert not os.path.exists(os.path.join(d, "note.txt"))
    assert api.Job(d).note == ""


def test_job_note_reads_note_txt(api, job_factory):
    """A note.txt in the job dir is read back, stripped of surrounding whitespace."""
    d = job_factory(name="j-110", meta={"id": "j-110", "repo": "/srv/repos/demo"})
    with open(os.path.join(d, "note.txt"), "w") as f:
        f.write("Use the existing helper, do not add a new one.\n")
    assert api.Job(d).note == "Use the existing helper, do not add a new one."


def test_step_brief_without_note_omits_note_block(api, job_factory):
    """step_brief does not mention a note when the job has none."""
    job = api.Job(job_factory(name="j-111", meta={"id": "j-111", "repo": "/srv/repos/demo"}))
    brief = step_brief(job, "1. write a.txt", "1. write a.txt\n")
    assert "Owner note" not in brief


def test_step_brief_appends_note_when_present(api, job_factory):
    """step_brief appends the job's note to the brief when note.txt is present."""
    d = job_factory(name="j-112", meta={"id": "j-112", "repo": "/srv/repos/demo"})
    with open(os.path.join(d, "note.txt"), "w") as f:
        f.write("Prefer the existing helper.\n")
    job = api.Job(d)
    brief = step_brief(job, "1. write a.txt", "1. write a.txt\n")
    assert "Owner note for this run:" in brief
    assert "Prefer the existing helper." in brief
