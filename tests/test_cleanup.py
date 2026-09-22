"""Cleanup: old finished jobs lose their large folders only, and rotation leaves the pacer's week whole."""
import json
import os
import time

from conftest import make_job_dir

from offload import budget, cleanup, status
from offload.clock import TS_FMT

NOW_TS = time.mktime(time.strptime("2026-09-20 12:00:00", TS_FMT))


def _days_ago(days):
    return time.strftime(TS_FMT, time.localtime(time.time() - days * 86400))


def _finished_job(root, name, state, days):
    job_dir = make_job_dir(root, name)
    for folder in cleanup.SWEPT_FOLDERS:
        os.makedirs(os.path.join(job_dir, folder))
    with open(os.path.join(job_dir, "events.jsonl"), "w") as f:
        f.write("{}\n")
    status.set_status(job_dir, state, finished=_days_ago(days))
    return job_dir


def _write_ledger(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(row if isinstance(row, str) else json.dumps(row) + "\n")


def test_an_old_finished_job_loses_its_large_folders_and_keeps_its_records(tmp_path):
    job_dir = _finished_job(tmp_path, "old", status.DONE, 20)
    assert cleanup.sweep_finished_jobs(tmp_path, 14) == ["old"]
    assert sorted(os.listdir(job_dir)) == ["events.jsonl", "job.md", "status.json"]
    record = status.job_status(job_dir)
    assert record["status"] == status.DONE and record["swept"]


def test_recent_running_and_already_swept_jobs_are_left_alone(tmp_path):
    _finished_job(tmp_path, "recent", status.DONE, 2)
    _finished_job(tmp_path, "running", status.RUNNING, 20)
    swept = _finished_job(tmp_path, "swept", status.FAILED, 20)
    status.set_status(swept, status.FAILED, swept="2026-01-01 00:00:00")
    no_time = make_job_dir(tmp_path, "no-time")
    status.set_status(no_time, status.DONE)
    assert cleanup.sweep_finished_jobs(tmp_path, 14) == []
    assert os.path.isdir(os.path.join(swept, "work"))


def test_keep_days_zero_turns_the_sweep_off_and_a_dry_run_removes_nothing(tmp_path):
    job_dir = _finished_job(tmp_path, "old", status.DONE, 20)
    assert cleanup.sweep_finished_jobs(tmp_path, 0) == []
    assert cleanup.sweep_finished_jobs(tmp_path, 14, dry_run=True) == ["old"]
    assert os.path.isdir(os.path.join(job_dir, "work"))
    assert "swept" not in status.job_status(job_dir)


def test_rotation_moves_only_lines_that_are_old_and_from_an_earlier_month(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    old = {"ts": NOW_TS - 40 * 86400, "job": "old", "model": "opus", "usd": 1.0}
    same_month = {"ts": NOW_TS - 18 * 86400, "job": "early-sept", "model": "opus", "usd": 2.0}
    recent = {"ts": NOW_TS - 3 * 86400, "job": "recent", "model": "sonnet", "usd": 4.0}
    _write_ledger(ledger, [old, "{not json\n", same_month, recent])
    assert cleanup.rotate_ledger(str(ledger), now_ts=NOW_TS) == 1
    assert json.loads((tmp_path / "ledger-2026-08.jsonl").read_text()) == old
    kept = ledger.read_text().splitlines()
    assert len(kept) == 3 and kept[0] == "{not json"


def test_the_last_eight_days_stay_even_across_a_month_boundary(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    first_of_month = time.mktime(time.strptime("2026-10-01 09:00:00", TS_FMT))
    _write_ledger(ledger, [{"ts": first_of_month - 3 * 86400, "job": "late-sept", "model": "opus", "usd": 1.0}])
    before = ledger.read_text()
    assert cleanup.rotate_ledger(str(ledger), now_ts=first_of_month) == 0
    assert ledger.read_text() == before
    assert cleanup.rotate_ledger(str(tmp_path / "missing.jsonl"), now_ts=NOW_TS) == 0


def test_job_costs_read_the_archives_and_the_pacer_reads_the_live_ledger_only(settings):
    _write_ledger(settings.ledger, [{"ts": NOW_TS - 40 * 86400, "job": "old", "model": "opus", "usd": 1.5},
                                    {"ts": NOW_TS - 86400, "job": "new", "model": "sonnet", "usd": 0.5}])
    cleanup.rotate_ledger(settings.ledger, now_ts=NOW_TS)
    costs = budget.job_costs()
    assert costs["old"][0] == 1.5 and costs["new"][0] == 0.5
    assert budget.spent_since(0) == 0.5
