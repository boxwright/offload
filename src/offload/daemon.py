"""The loop: watch the jobs root and work through it, one job at a time.

A job that must wait (for the owner, a provider limit, or the budget) is parked: its status holds the wake
condition, and the loop runs the next job. A parked job goes again when its wake condition is true.
"""
import os
import time

from offload import inbound, jobs, status
from offload.cleanup import run_cleanup
from offload.clock import is_past, now
from offload.config import get_config
from offload.engine import EXIT_EXCEPTION, EXIT_OK, run
from offload.intake import intake
from offload.report import write_report
from offload.sandbox import kill_leftover_containers


def _requeue_interrupted(jobs_root):
    """After a restart, a job that was running goes back in the queue and continues from its checkpoint.

    A parked job needs nothing: its wake condition is on disk.
    """
    for job_dir in jobs.job_dirs(jobs_root, include_hidden=True):
        record = status.job_status(job_dir)
        if record.get("status") == status.RUNNING:
            status.set_status(job_dir, status.READY, restarted=record.get("restarted", 0) + 1)
            print(f"[{now()}] requeued {os.path.basename(job_dir)} after restart", flush=True)


_finished = {}         # job dir -> mtime of its status.json when it was seen done or failed; re-read only on change


def _status_mtime(job_dir):
    try:
        return os.stat(os.path.join(job_dir, "status.json")).st_mtime_ns
    except OSError:
        return None


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
    for job_dir in jobs.job_dirs(jobs_root):
        mtime = _status_mtime(job_dir)
        if job_dir in _finished and _finished[job_dir] == mtime:
            continue
        _finished.pop(job_dir, None)          # a changed status file (offload retry) is read again
        record = status.job_status(job_dir)
        state = record.get("status")
        if state in (status.DONE, status.FAILED):
            _finished[job_dir] = mtime
        elif _is_runnable(job_dir, record):
            runnable.append((state, job_dir))
    for state, job_dir in runnable:
        if state == status.INBOX:
            return state, job_dir
    return runnable[0] if runnable else None


def _park(job_dir, parked):
    jobs.Job(job_dir).event("parked", status=parked.status, **parked.wake)
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
        jobs.Job(job_dir).event("fail", reason=f"exception: {str(exc)[:200]}")
        exit_code = EXIT_EXCEPTION
    status.set_status(job_dir, status.DONE if exit_code == EXIT_OK else status.FAILED,
                      rc=exit_code, finished=now())
    try:
        write_report(jobs.Job(job_dir), exit_code)
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


INBOUND_POLL_S = 30     # how often the channel is read while a gate is open
_last_poll = 0.0        # epoch seconds; 0.0 before the first poll
_last_message_id = 0    # the largest message id seen; a poll starts after it


def _open_gates(jobs_root):
    """The (job dir, record) pairs of jobs waiting on the owner, oldest job name first.

    A gate that already has an answer.txt is not open: that answer is read when the job next wakes.
    """
    gates = []
    for job_dir in jobs.job_dirs(jobs_root):
        record = status.job_status(job_dir)
        if record.get("status") != status.WAITING_OWNER:
            continue
        if os.path.exists(os.path.join(job_dir, "answer.txt")):
            continue
        gates.append((job_dir, record))
    return gates


def _match_gate(gates, text):
    """Match a reply to one open gate: (job dir, answer text) on a match, else (None, reason).

    The text must start with a job id (the directory name) or a prefix of one, followed by a space or the
    end of the text; the rest is the answer. A prefix that fits exactly one gate is used even when it is
    the only gate open, so a reply that names its job is stripped of the name. When nothing fits and one
    gate is open, the whole text is the answer. A miss is "no job id" or "ambiguous".
    """
    token, _, rest = text.partition(" ")
    matches = [job_dir for job_dir, _ in gates
               if os.path.basename(job_dir) == token or os.path.basename(job_dir).startswith(token)]
    if len(matches) == 1:
        return matches[0], rest
    if len(matches) > 1:
        return None, "ambiguous"
    if len(gates) == 1:
        return gates[0][0], text
    return None, "no job id"


def _collect_answers(jobs_root, inbox):
    """Read the channel while a gate is open, at most once every INBOUND_POLL_S. Returns the answers written.

    A reply is written as the matched job's answer.txt and acknowledged with a check mark. A reply that
    matches no gate, or more than one, is logged as answer_ignored on the oldest open gate and skipped.
    """
    global _last_poll, _last_message_id
    if inbox is None:
        return 0
    gates = _open_gates(jobs_root)
    if not gates or time.time() - _last_poll < INBOUND_POLL_S:
        return 0
    _last_poll = time.time()
    gate_wait_s = get_config().gate_wait_s
    asked = min(record["deadline"] - gate_wait_s for _, record in gates)
    after = max(_last_message_id, inbound.snowflake_after(asked))
    written = 0
    for message in inbox.messages_after(after):
        _last_message_id = max(_last_message_id, int(message["id"]))
        job_dir, result = _match_gate(gates, message["text"])
        if job_dir is None:
            jobs.Job(gates[0][0]).event("answer_ignored", message_id=message["id"], reason=result)
            continue
        jobs.answer(job_dir, result)
        jobs.Job(job_dir).event("answer_from_chat", message_id=message["id"], text=result[:200])
        inbox.acknowledge(message["id"])
        gates = [gate for gate in gates if gate[0] != job_dir]
        written += 1
    return written


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
    inbox = inbound.make_inbox(get_config())     # None when the bot token is not configured
    while True:
        try:
            _collect_answers(jobs_root, inbox)
        except Exception as exc:     # the inbox must never stop the loop
            print(f"[{now()}] answer poll failed: {exc}", flush=True)
        picked = None if os.path.exists(get_config().pause_file) else _next_job(jobs_root)
        if picked is None:
            _cleanup_once_a_day(jobs_root)
            time.sleep(interval)
            continue
        state, job_dir = picked
        if state in status.WAITING:
            jobs.Job(job_dir).event("woken", was=state)
        if jobs.Job(job_dir).repo:
            _run_and_report(job_dir)
        else:
            _intake(job_dir)
