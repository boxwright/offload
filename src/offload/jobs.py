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


class JobError(Exception):
    """A job.md that cannot be parsed into a Job. The daemon fails the job; it never takes the loop down."""


class Job:
    """One unit of work. `dir` holds its files; `work` is the clone the workers edit."""

    def __init__(self, job_dir):
        self.dir = os.path.abspath(job_dir)
        self.work = self.path("work")
        self.events = self.path("events.jsonl")
        self.plan = self.path("plan.md")
        text = read_text(self.path("job.md"))
        match = _FRONT_MATTER_RE.match(text)
        block = match.group(1) if match else ""
        self.meta = _parse_front_matter(block) if match else {}
        self.body = match.group(2) if match else text
        self.id = self.meta.get("id") or os.path.basename(self.dir)
        self.title = self.meta.get("title", "")
        self.repo = self.meta.get("repo", "")
        self.test_cmd = self.meta.get("test", DEFAULT_TEST_CMD)
        self.branch = self.meta.get("branch", f"offload/{self.id}")
        self.checks = _parse_checks(block)

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


def _parse_checks(block):
    """The optional `checks` key: the spec checks, a list of shell commands.

    Written inline (`checks: [a, b]`) or as indented `- ` lines under a bare `checks:`. Absent -> [].
    A value that is not a list of non-empty strings raises a JobError naming `checks`.
    """
    lines = block.splitlines()
    for i, line in enumerate(lines):
        key, sep, rest = line.partition(":")
        if not sep or key.strip() != "checks":
            continue
        value = rest.strip()
        if value:
            return _inline_checks(value)
        items = []
        for next_line in lines[i + 1:]:
            if not next_line.startswith(" "):
                break
            match = re.match(r"\s*-\s+(.*)", next_line)
            if match:
                items.append(match.group(1).strip().strip('"').strip("'"))
        return _valid_checks(items)
    return []


def _inline_checks(value):
    """An inline bracketed list: `[a, b]`. Anything else is not a list."""
    if not (value.startswith("[") and value.endswith("]")):
        raise JobError(f"checks must be a list of commands, e.g. `checks: [cmd]` (got {value!r})")
    inner = value[1:-1].strip()
    if not inner:
        return []
    return _valid_checks([item.strip().strip('"').strip("'") for item in inner.split(",")])


def _valid_checks(items):
    for item in items:
        if not item:
            raise JobError("checks: every entry must be a non-empty command string")
    return items


def job_dirs(jobs_root, include_hidden=False):
    """Job directories under the root, oldest name first. Names starting with `_` are templates."""
    with os.scandir(jobs_root) as entries:
        names = sorted(entry.name for entry in entries if entry.is_dir())
    return [os.path.join(jobs_root, name) for name in names if include_hidden or not name.startswith("_")]


def slugify(text):
    """A readable id fragment: the ASCII words of `text`, lowercased, joined by hyphens, cut at a word boundary
    to at most 32 characters. Raises ValueError naming `text` when no ASCII word remains."""
    slug = ""
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > 32:
            break
        slug = candidate
    if not slug:
        raise ValueError(f"no ASCII words to slugify in {text!r}")
    return slug


def _next_id(jobs_root, base):
    """`base`, or `base-2`, `base-3`, ... while a directory of that name exists."""
    job_id, suffix = base, 1
    while os.path.exists(os.path.join(jobs_root, job_id)):
        suffix += 1
        job_id = f"{base}-{suffix}"
    return job_id


def resolve_job_id(jobs_root, text):
    """The one job id that `text` names: an exact id, or a prefix that fits exactly one job.

    An exact match wins even when it prefixes other ids. Nothing matching raises KeyError naming `text`;
    more than one match raises ValueError listing the candidates.
    """
    names = [os.path.basename(d) for d in job_dirs(jobs_root)]
    if text in names:
        return text
    matches = sorted(name for name in names if name.startswith(text))
    if not matches:
        raise KeyError(text)
    if len(matches) > 1:
        raise ValueError(f"ambiguous job id prefix {text!r}: {', '.join(matches)}")
    return matches[0]


def _parse_spec(spec_file):
    """A `job.md`-style spec file: its front matter mapping and its body (Goal / Done when)."""
    text = read_text(spec_file)
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    return _parse_front_matter(match.group(1)), match.group(2)


def add(jobs_root, text, spec_file=None, confirm=False, slug=None):
    """Queue a job. A one-line `text` lands in the inbox for intake to draft.

    The id is `j<date>-<slug>` when the title gives a slug (a spec file's title, or `slug`), else the
    `j<date>-<time>` stamp, because a one-liner has no title until intake runs; either way `-2`, `-3`, ...
    while the directory exists. A job directory is never renamed later.

    A `job.md`-style `spec_file` is copied straight into the new job's `job.md` with its
    `id`/`branch`/`test` filled in and the status set to `ready`, so intake's Claude call is
    skipped. `confirm=True` writes `confirm: true` into the front matter on either path.
    """
    if spec_file is not None and slug is None:
        try:
            slug = slugify(_parse_spec(spec_file)[0].get("title", ""))
        except ValueError:
            slug = None
    base = f"j{time.strftime('%Y%m%d')}-{slug}" if slug else time.strftime("j%Y%m%d-%H%M%S")
    job_id = _next_id(jobs_root, base)
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
