"""The report's `## Checks` section: one line per spec check from the `check` events, the captured
output under each failure, and the whole section absent when the job ran no checks.

Job dirs are built under tmp_path, so no test touches the network, Docker, or the real home directory.
"""
import os

from conftest import make_job_dir

from offload import report
from offload.files import append_jsonl
from offload.jobs import Job


def _add_check(job_dir, command, exit_code, output=""):
    """One `check` event, the same shape the engine writes after the push."""
    append_jsonl(os.path.join(job_dir, "events.jsonl"),
                 {"t": "2026-09-24 12:00:00", "job": "rpt", "kind": "check",
                  "command": command, "exit": exit_code, "output": output})


def _write_report(job_dir, exit_code=0):
    report.write_report(Job(job_dir), exit_code)
    with open(os.path.join(job_dir, "REPORT.md")) as f:
        return f.read()


def test_all_checks_pass_lists_each_as_pass(tmp_path):
    """Every check exits 0: the section lists each command as pass, with no output."""
    job_dir = make_job_dir(tmp_path, "rpt-ok", {"id": "rpt-ok", "repo": "/srv/repos/demo"})
    _add_check(job_dir, "make lint", 0, "ok\n")
    _add_check(job_dir, "make test", 0, "ok\n")
    text = _write_report(job_dir)
    assert "## Checks" in text
    assert "- pass: `make lint`" in text
    assert "- pass: `make test`" in text
    assert "fail" not in text.split("## Checks")[1]


def test_a_failing_check_lists_fail_with_its_output(tmp_path):
    """A non-zero check: the section names it as fail and carries the captured output."""
    job_dir = make_job_dir(tmp_path, "rpt-bad", {"id": "rpt-bad", "repo": "/srv/repos/demo"})
    _add_check(job_dir, "make lint", 0, "ok\n")
    _add_check(job_dir, "make test", 1, "FAIL: 2 tests failed\n")
    text = _write_report(job_dir, exit_code=12)
    section = text.split("## Checks")[1]
    assert "- pass: `make lint`" in section
    assert "- fail: `make test`" in section
    assert "FAIL: 2 tests failed" in section
    # the pass line carries no output
    assert "ok" not in section.split("- fail")[0]


def test_a_job_without_check_events_has_no_checks_section(tmp_path):
    """No `check` events: the report is written without a `## Checks` heading at all."""
    job_dir = make_job_dir(tmp_path, "rpt-plain", {"id": "rpt-plain", "repo": "/srv/repos/demo"})
    text = _write_report(job_dir)
    assert "## Checks" not in text
