"""Housekeeping: old finished jobs lose their large folders, and old ledger lines move to monthly archives.

A job's records (job.md, plan, events, report, status) are never removed. The live ledger always keeps
the last eight days, so the pacer's week is complete, and `budget.job_costs` reads the archives too.
"""
import json
import os
import shutil
import time

from offload import status
from offload.clock import TS_FMT, now
from offload.config import get_config
from offload.jobs import job_dirs

SWEPT_FOLDERS = ("work", "claude-home", "scratch")
LEDGER_KEEP_S = 8 * 86400


def _finished_at(record):
    """The job's `finished` time as epoch seconds, or None when it is missing or unreadable."""
    try:
        return time.mktime(time.strptime(record.get("finished"), TS_FMT))
    except (TypeError, ValueError):
        return None


def sweep_finished_jobs(jobs_root, keep_days, dry_run=False):
    """Remove work/, claude-home/ and scratch/ from jobs that finished more than `keep_days` days ago.

    Returns the ids of the jobs swept, or that a real run would sweep. `keep_days` of 0 or less turns the
    sweep off. A job with no readable `finished` time is left alone.
    """
    if keep_days <= 0:
        return []
    cutoff = time.time() - keep_days * 86400
    swept = []
    for job_dir in job_dirs(jobs_root):
        record = status.job_status(job_dir)
        state = record.get("status")
        finished = _finished_at(record)
        if state not in (status.DONE, status.FAILED) or record.get("swept") or finished is None:
            continue
        if finished >= cutoff:
            continue
        if not dry_run:
            for name in SWEPT_FOLDERS:
                shutil.rmtree(os.path.join(job_dir, name), ignore_errors=True)
            status.set_status(job_dir, state, swept=now())
        swept.append(os.path.basename(job_dir))
    return swept


def _archive_month(line, cutoff, this_month):
    """The (year, month) archive a ledger line moves to, or None when the line stays."""
    try:
        stamp = json.loads(line).get("ts")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(stamp, (int, float)) or stamp >= cutoff:
        return None
    month = time.localtime(stamp)[:2]
    return month if month < this_month else None


def rotate_ledger(ledger_path, keep_s=LEDGER_KEEP_S, now_ts=None):
    """Move ledger lines that are older than `keep_s` and from an earlier calendar month to `ledger-YYYY-MM.jsonl`.

    Returns the number of lines moved. A line that cannot be dated stays. The archives are written first and
    the ledger is replaced last, so a crash can duplicate a line in an archive but never lose one.
    """
    if not os.path.exists(ledger_path):
        return 0
    now_ts = time.time() if now_ts is None else now_ts
    this_month = time.localtime(now_ts)[:2]
    kept = []
    moved = {}
    with open(ledger_path) as ledger:
        for line in ledger:
            month = _archive_month(line, now_ts - keep_s, this_month)
            if month is None:
                kept.append(line)
            else:
                moved.setdefault(month, []).append(line)
    if not moved:
        return 0
    stem, ext = os.path.splitext(ledger_path)
    for (year, month), lines in moved.items():
        with open(f"{stem}-{year:04d}-{month:02d}{ext}", "a") as archive:
            archive.writelines(lines)
    tmp = f"{ledger_path}.tmp"
    with open(tmp, "w") as ledger:
        ledger.writelines(kept)
    os.replace(tmp, ledger_path)
    return sum(len(lines) for lines in moved.values())


def run_cleanup(jobs_root, dry_run=False):
    """Sweep old jobs and rotate the ledger. A dry run changes nothing. Returns (swept job ids, ledger lines moved)."""
    swept = sweep_finished_jobs(jobs_root, get_config().keep_days, dry_run=dry_run)
    if dry_run:
        print(f"cleanup (dry run): would sweep {len(swept)} job(s): {', '.join(swept) or 'none'}")
        return swept, 0
    moved = rotate_ledger(get_config().ledger)
    print(f"cleanup: swept {len(swept)} job(s), moved {moved} ledger line(s)", flush=True)
    return swept, moved
