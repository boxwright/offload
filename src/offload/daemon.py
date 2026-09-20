"""The loop: watch the jobs root and work through it, one job at a time."""
import os
import time

from offload import status
from offload.clock import now
from offload.config import CFG
from offload.engine import EXIT_EXCEPTION, EXIT_OK, run
from offload.intake import intake
from offload.jobs import Job, job_dirs
from offload.report import write_report


def _requeue_interrupted(jobs_root):
    """After a restart, a job that was running or waiting goes back in the queue."""
    for job_dir in job_dirs(jobs_root, include_hidden=True):
        record = status.job_status(job_dir)
        if record.get("status") in status.INTERRUPTED:
            status.set_status(job_dir, status.READY, restarted=record.get("restarted", 0) + 1)
            print(f"[{now()}] requeued {os.path.basename(job_dir)} after restart", flush=True)


_finished = set()      # job directories known to be done or failed; never re-read


def _next_job(jobs_root):
    """The oldest inbox job, else the oldest ready job, else None. Returns (status, job dir)."""
    states = []
    for job_dir in job_dirs(jobs_root):
        if job_dir in _finished:
            continue
        state = status.job_status(job_dir).get("status")
        if state in (status.DONE, status.FAILED):
            _finished.add(job_dir)
        else:
            states.append((state, job_dir))
    for wanted in (status.INBOX, status.READY):
        for state, job_dir in states:
            if state == wanted:
                return state, job_dir
    return None


def _run_and_report(job_dir):
    status.set_status(job_dir, status.RUNNING, started=now())
    try:
        exit_code = run(job_dir)
    except Exception as exc:     # one bad job must never take the loop down
        Job(job_dir).event("fail", reason=f"exception: {str(exc)[:200]}")
        exit_code = EXIT_EXCEPTION
    status.set_status(job_dir, status.DONE if exit_code == EXIT_OK else status.FAILED,
                      rc=exit_code, finished=now())
    try:
        write_report(Job(job_dir), exit_code)
    except Exception as exc:     # a report is never worth a crash
        print(f"[{now()}] report failed for {os.path.basename(job_dir)}: {exc}", flush=True)


def serve(jobs_root, interval=20):
    """Watch the jobs root and work through it, one job at a time, until stopped.

    An inbox job goes through intake, a ready job is run. While the pause file exists nothing new starts.
    """
    os.makedirs(os.path.dirname(CFG.pause_file), exist_ok=True)
    print(f"[{now()}] offload serve: watching {jobs_root}", flush=True)
    _requeue_interrupted(jobs_root)
    while True:
        picked = None if os.path.exists(CFG.pause_file) else _next_job(jobs_root)
        if picked is None:
            time.sleep(interval)
            continue
        state, job_dir = picked
        if state == status.READY:
            _run_and_report(job_dir)
            continue
        try:
            intake(job_dir)
        except Exception as exc:     # one bad job must never take the loop down
            print(f"[{now()}] intake failed for {os.path.basename(job_dir)}: {exc}", flush=True)
            status.set_status(job_dir, status.FAILED, reason=f"intake exception: {str(exc)[:160]}")
