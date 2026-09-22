"""The loop: watch the jobs root and work through it, one job at a time.

A job that must wait (for the owner, a provider limit, or the budget) is parked: its status holds the wake
condition, and the loop runs the next job. A parked job goes again when its wake condition is true.
"""
import os
import time

from offload import status
from offload.cleanup import run_cleanup
from offload.clock import is_past, now
from offload.config import get_config
from offload.engine import EXIT_EXCEPTION, EXIT_OK, run
from offload.intake import intake
from offload.jobs import Job, job_dirs
from offload.report import write_report
from offload.sandbox import kill_leftover_containers


def _requeue_interrupted(jobs_root):
    """After a restart, a job that was running goes back in the queue and continues from its checkpoint.

    A parked job needs nothing: its wake condition is on disk.
    """
    for job_dir in job_dirs(jobs_root, include_hidden=True):
        record = status.job_status(job_dir)
        if record.get("status") == status.RUNNING:
            status.set_status(job_dir, status.READY, restarted=record.get("restarted", 0) + 1)
            print(f"[{now()}] requeued {os.path.basename(job_dir)} after restart", flush=True)


_finished = set()      # job directories known to be done or failed; never re-read


def _is_runnable(job_dir, record):
    """An inbox or ready job, or a parked job whose wake condition is true."""
    state = record.get("status")
    if state == status.WAITING_OWNER:
        answered = os.path.exists(os.path.join(job_dir, "answer.txt"))
        return answered or time.time() >= (record.get("deadline") or 0)
    if state in (status.WAITING_LIMIT, status.WAITING_BUDGET):
        return is_past(record.get("until"))
    return state in (status.INBOX, status.READY)


def _next_job(jobs_root):
    """The oldest inbox job, else the oldest other runnable job, else None. Returns (status, job dir)."""
    runnable = []
    for job_dir in job_dirs(jobs_root):
        if job_dir in _finished:
            continue
        record = status.job_status(job_dir)
        state = record.get("status")
        if state in (status.DONE, status.FAILED):
            _finished.add(job_dir)
        elif _is_runnable(job_dir, record):
            runnable.append((state, job_dir))
    for state, job_dir in runnable:
        if state == status.INBOX:
            return state, job_dir
    return runnable[0] if runnable else None


def _park(job_dir, parked):
    Job(job_dir).event("parked", status=parked.status, **parked.wake)
    status.set_status(job_dir, parked.status, **parked.wake)


def _run_and_report(job_dir):
    started = status.job_status(job_dir).get("started") or now()
    status.set_status(job_dir, status.RUNNING, started=started)
    try:
        exit_code = run(job_dir)
    except status.Parked as parked:
        _park(job_dir, parked)
        return
    except Exception as exc:     # one bad job must never take the loop down
        Job(job_dir).event("fail", reason=f"exception: {str(exc)[:200]}")
        exit_code = EXIT_EXCEPTION
    status.set_status(job_dir, status.DONE if exit_code == EXIT_OK else status.FAILED,
                      rc=exit_code, finished=now())
    try:
        write_report(Job(job_dir), exit_code)
    except Exception as exc:     # a report is never worth a crash
        print(f"[{now()}] report failed for {os.path.basename(job_dir)}: {exc}", flush=True)


def _intake(job_dir):
    try:
        intake(job_dir)
    except status.Parked as parked:
        _park(job_dir, parked)
    except Exception as exc:     # one bad job must never take the loop down
        print(f"[{now()}] intake failed for {os.path.basename(job_dir)}: {exc}", flush=True)
        status.set_status(job_dir, status.FAILED, reason=f"intake exception: {str(exc)[:160]}")


_last_cleanup = 0.0     # epoch seconds; 0.0 before the first cleanup


def _cleanup_once_a_day(jobs_root):
    """Housekeeping while the loop is idle, at most once in 24 hours. A failure prints and waits for the next day."""
    global _last_cleanup
    if time.time() - _last_cleanup < 86400:
        return
    _last_cleanup = time.time()
    try:
        run_cleanup(jobs_root)
    except Exception as exc:     # housekeeping is never worth a crash
        print(f"[{now()}] cleanup failed: {exc}", flush=True)


def serve(jobs_root, interval=20):
    """Watch the jobs root and work through it, one job at a time, until stopped.

    A job with no repository yet goes through intake; any other job is run. While the pause file exists
    nothing new starts.
    """
    os.makedirs(os.path.dirname(get_config().pause_file), exist_ok=True)
    print(f"[{now()}] offload serve: watching {jobs_root}", flush=True)
    try:
        killed = kill_leftover_containers()
    except Exception as exc:     # no Docker yet is a problem for the first job, not for the loop
        print(f"[{now()}] leftover container check failed: {exc}", flush=True)
    else:
        if killed:
            print(f"[{now()}] killed {killed} worker container(s) left by the previous daemon", flush=True)
    _requeue_interrupted(jobs_root)
    while True:
        picked = None if os.path.exists(get_config().pause_file) else _next_job(jobs_root)
        if picked is None:
            _cleanup_once_a_day(jobs_root)
            time.sleep(interval)
            continue
        state, job_dir = picked
        if state in status.WAITING:
            Job(job_dir).event("woken", was=state)
        if Job(job_dir).repo:
            _run_and_report(job_dir)
        else:
            _intake(job_dir)
