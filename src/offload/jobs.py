"""The job: a directory holding `job.md` (front matter and a goal) and everything the engine writes about it."""
import os
import re
import time

from offload import status
from offload.clock import now
from offload.config import get_config
from offload.files import append_jsonl, read_text, write_text
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


def known_repos():
    """The repositories intake may choose from (`repos_file`): path or URL -> one line on what it is."""
    if not os.path.exists(get_config().repos_file):
        return {}
    import yaml
    with open(get_config().repos_file) as f:
        return yaml.safe_load(f) or {}


def add(jobs_root, text):
    """Queue a one-line idea. Intake turns it into a full job file."""
    text = text.strip()
    stamp = time.strftime("j%Y%m%d-%H%M%S")
    job_id, suffix = stamp, 1
    while os.path.exists(os.path.join(jobs_root, job_id)):
        suffix += 1
        job_id = f"{stamp}-{suffix}"
    job_dir = os.path.join(jobs_root, job_id)
    os.makedirs(job_dir)
    write_text(os.path.join(job_dir, "job.md"), f"---\nid: {job_id}\ntitle: {text[:80]}\n---\n## Goal\n{text}\n")
    status.set_status(job_dir, status.INBOX)
    print(f"added {job_id}: {text[:80]}")
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
