"""The job: a directory holding `job.md` (front matter and a goal) and everything the engine writes about it."""
import os
import re
import time

from offload import status
from offload.clock import now
from offload.files import append_jsonl, read_text, remove_if_exists, write_text
from offload.notify import notify

_FRONT_MATTER_RE = re.compile(r"---\n(.*?)\n---\n(.*)", re.S)
DEFAULT_TEST_CMD = "python3 -m pytest -q"


class Job:
    """One unit of work. `dir` holds its files; `work` is the clone the workers edit."""

    def __init__(self, job_dir):
        self.dir = os.path.abspath(job_dir)
        self.work = self.path("work")
        self.events = self.path("events.jsonl")
        self.plan = self.path("plan.md")
        text = read_text(self.path("job.md"))
        match = _FRONT_MATTER_RE.match(text)
        self.meta = _parse_front_matter(match.group(1)) if match else {}
        self.body = match.group(2) if match else text
        self.id = self.meta.get("id") or os.path.basename(self.dir)
        self.title = self.meta.get("title", "")
        self.repo = self.meta.get("repo", "")
        self.test_cmd = self.meta.get("test", DEFAULT_TEST_CMD)
        self.branch = self.meta.get("branch", f"offload/{self.id}")

    def path(self, name):
        return os.path.join(self.dir, name)

    @property
    def note(self):
        """The owner's note for the next run, read from an optional `note.txt`. Empty when absent."""
        try:
            return read_text(self.path("note.txt")).strip()
        except FileNotFoundError:
            return ""

    def flag(self, key):
        """A true/false front matter key such as `public` or `allow_test_edits`."""
        return str(self.meta.get(key, "false")).lower() == "true"

    def event(self, kind, **fields):
        """Append one record to events.jsonl and echo it to the daemon log. A `fail` also notifies the owner."""
        record = {"t": now(), "job": self.id, "kind": kind, **fields}
        append_jsonl(self.events, record)
        shown = " ".join(f"{key}={str(value)[:60]!r}" for key, value in fields.items() if key != "text")
        print(f"[{record['t']}] {kind} {shown}", flush=True)
        if kind == "fail":
            notify(self, f"[{self.id}] FAILED: {fields.get('reason', '')}"[:300])


def _parse_front_matter(block):
    """Top-level `key: value` lines only. Values keep no surrounding quotes."""
    meta = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"')
    return meta


def job_dirs(jobs_root, include_hidden=False):
    """Job directories under the root, oldest name first. Names starting with `_` are templates."""
    with os.scandir(jobs_root) as entries:
        names = sorted(entry.name for entry in entries if entry.is_dir())
    return [os.path.join(jobs_root, name) for name in names if include_hidden or not name.startswith("_")]


def _parse_spec(spec_file):
    """A `job.md`-style spec file: its front matter mapping and its body (Goal / Done when)."""
    text = read_text(spec_file)
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    return _parse_front_matter(match.group(1)), match.group(2)


def add(jobs_root, text, spec_file=None, confirm=False):
    """Queue a job. A one-line `text` lands in the inbox for intake to draft.

    A `job.md`-style `spec_file` is copied straight into the new job's `job.md` with its
    `id`/`branch`/`test` filled in and the status set to `ready`, so intake's Claude call is
    skipped. `confirm=True` writes `confirm: true` into the front matter on either path.
    """
    stamp = time.strftime("j%Y%m%d-%H%M%S")
    job_id, suffix = stamp, 1
    while os.path.exists(os.path.join(jobs_root, job_id)):
        suffix += 1
        job_id = f"{stamp}-{suffix}"
    job_dir = os.path.join(jobs_root, job_id)
    os.makedirs(job_dir)
    if spec_file is not None:
        meta, body = _parse_spec(spec_file)
        front = dict(meta)
        front["id"] = job_id
        front.setdefault("branch", f"offload/{job_id}")
        front.setdefault("test", DEFAULT_TEST_CMD)
        if confirm:
            front["confirm"] = "true"
        header = "\n".join(f"{key}: {value}" for key, value in front.items())
        write_text(os.path.join(job_dir, "job.md"), f"---\n{header}\n---\n{body}")
        state = status.READY
        title = meta.get("title") or meta.get("id") or job_id
    else:
        text = text.strip()
        front = {"id": job_id, "title": text[:80]}
        if confirm:
            front["confirm"] = "true"
        header = "\n".join(f"{key}: {value}" for key, value in front.items())
        write_text(os.path.join(job_dir, "job.md"), f"---\n{header}\n---\n## Goal\n{text}\n")
        state = status.INBOX
        title = text[:80]
    status.set_status(job_dir, state)
    print(f"added {job_id}: {title}")
    return job_id


def cancel(job_dir):
    """Cancel a job. A queued or parked job fails at once. A running job stops before its next worker call,
    and its current worker container is killed so that call ends now."""
    from offload.sandbox import kill_leftover_containers
    job_dir = os.path.abspath(job_dir)
    write_text(os.path.join(job_dir, "cancel"), now() + "\n")
    state = status.job_status(job_dir).get("status")
    if state == status.RUNNING:
        kill_leftover_containers()
        print("cancel recorded: the running job stops before its next worker call")
    elif state in (status.DONE, status.FAILED):
        print(f"the job is already {state}")
    else:
        status.set_status(job_dir, status.FAILED, reason="cancelled by the owner", finished=now())
        print("cancelled")


def answer(job_dir, text):
    """Record the owner's answer to the job's open gate."""
    path = os.path.join(os.path.abspath(job_dir), "answer.txt")
    write_text(path, text.strip() + "\n")
    print(f"answer recorded: {path}")


def retry(job_dir, note=None, replan=False):
    """Re-queue a failed job: clear the run's leftovers and set it back to ready, reusing the stored spec.

    The job must be `failed`; anything else is refused and its current state is named. `note`, when given,
    is written to `note.txt` so the next run's brief carries it. The checkpoint and the terminal report's
    leftovers go; the stored plan goes only when `replan` is set. `job.md` and `intake.json` are always
    kept, so the daemon re-runs the job without another intake call. Returns 0 on success, 1 when refused.
    """
    job_dir = os.path.abspath(job_dir)
    state = status.job_status(job_dir).get("status")
    if state != status.FAILED:
        print(f"cannot retry: the job is {state}, not failed")
        return 1
    if note is not None:
        write_text(os.path.join(job_dir, "note.txt"), note.strip() + "\n")
    for name in ("progress.json", "cancel", "answer.txt", "REPORT.md"):
        remove_if_exists(os.path.join(job_dir, name))
    if replan:
        for name in ("plan.txt", "plan.md"):
            remove_if_exists(os.path.join(job_dir, name))
    status.set_status(job_dir, status.READY, retried=now())
    print(f"requeued {os.path.basename(job_dir)}" + (" (plan will be made again)" if replan else ""))
    return 0
