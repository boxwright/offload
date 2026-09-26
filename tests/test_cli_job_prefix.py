"""CLI-level tests for job id prefix resolution in `_job_dir`.

`report`, `answer`, `cancel` (and any future `retry`) accept a unique prefix of a job id:
`_job_dir` resolves a non-path argument against the jobs root, while paths and full ids keep
working unchanged, and the resolver's error is printed as a clean message rather than a
traceback.
"""
from conftest import make_job_dir

from offload import cli


def test_report_on_a_unique_prefix_prints_the_full_report(settings, capsys):
    """A prefix that matches exactly one job id prints that job's REPORT.md."""
    job_dir = make_job_dir(settings.jobs_root, "j20260101-alpha", meta={"id": "j20260101-alpha"})
    make_job_dir(settings.jobs_root, "j20260102-beta", meta={"id": "j20260102-beta"})
    with open(job_dir + "/REPORT.md", "w") as f:
        f.write("The full report for j20260101-alpha.\n")
    rc = cli.main(["report", "j20260101-al"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "The full report for j20260101-alpha." in out


def test_report_on_an_ambiguous_prefix_errors_with_both_candidates(settings, capsys):
    """A prefix shared by two job ids errors, naming both candidates, with no traceback."""
    make_job_dir(settings.jobs_root, "j20260101-alpha", meta={"id": "j20260101-alpha"})
    make_job_dir(settings.jobs_root, "j20260101-alphabet", meta={"id": "j20260101-alphabet"})
    rc = cli.main(["report", "j20260101-al"])
    err = capsys.readouterr().err
    assert rc != 0
    assert "j20260101-alpha" in err
    assert "j20260101-alphabet" in err
    assert "Traceback" not in err


def test_report_on_a_no_match_prefix_errors_cleanly(settings, capsys):
    """A prefix that matches nothing prints a clean message naming it, with no traceback."""
    make_job_dir(settings.jobs_root, "j20260101-alpha", meta={"id": "j20260101-alpha"})
    rc = cli.main(["report", "zzz"])
    err = capsys.readouterr().err
    assert rc != 0
    assert "zzz" in err
    assert "Traceback" not in err


def test_report_on_a_full_id_still_works(settings, capsys):
    """A full job id resolves to itself, unchanged by the prefix feature."""
    job_dir = make_job_dir(settings.jobs_root, "j20260101-alpha", meta={"id": "j20260101-alpha"})
    make_job_dir(settings.jobs_root, "j20260101-alpha-2", meta={"id": "j20260101-alpha-2"})
    with open(job_dir + "/REPORT.md", "w") as f:
        f.write("Report for the full id.\n")
    rc = cli.main(["report", "j20260101-alpha"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Report for the full id." in out


def test_report_on_a_path_still_works(settings, capsys):
    """A path to a job directory is used as it is, unchanged by the prefix feature."""
    job_dir = make_job_dir(settings.jobs_root, "j20260101-alpha", meta={"id": "j20260101-alpha"})
    with open(job_dir + "/REPORT.md", "w") as f:
        f.write("Report for the path.\n")
    rc = cli.main(["report", job_dir])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Report for the path." in out
