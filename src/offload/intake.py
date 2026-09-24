"""Intake: turn a one-line idea into a full job file, asking the owner only when the repository is unclear."""
import json
import os
import re

import yaml

from offload import notify, status
from offload.files import read_json, write_json, write_text
from offload.jobs import DEFAULT_TEST_CMD, Job
from offload.prompts import intake_prompt
from offload.repos import known_repos
from offload.workers import claude

_FENCE_RE = re.compile(r"```(?:yaml|yml)?\s*\n(.*?)```", re.S)
_KEY_LINE_RE = re.compile(r"^[A-Za-z_]+\s*:", re.M)


def _mapping(candidate):
    try:
        data = yaml.safe_load(candidate)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def extract_yaml(text):
    """The job mapping in a model's reply: inside a code fence if there is one, else from the first
    `key:` line from which the rest parses as a mapping that names a repo or a title."""
    fence = _FENCE_RE.search(text)
    if fence:
        return _mapping(fence.group(1))
    for key_line in _KEY_LINE_RE.finditer(text):
        data = _mapping(text[key_line.start():])
        if data and ("repo" in data or "title" in data):
            return data
    return None


def intake(job_dir):
    """Returns True when the job is ready to run."""
    job = Job(job_dir)
    if job.repo:
        status.set_status(job_dir, status.READY)
        return True
    request = job.body.strip()
    spec = _drafted_spec(job, request)
    if spec is None:
        status.set_status(job_dir, status.FAILED, reason="intake parse")
        return False
    if str(spec.get("repo", "UNKNOWN")).upper() == "UNKNOWN":
        answer = notify.ask_owner(job, "intake", f"Which repository is `{request[:120]}` about? "
                                                 "Reply with a path or git URL, or `skip`.")
        if not answer or answer.strip().lower() == "skip":
            status.set_status(job_dir, status.FAILED, reason="no repo")
            return False
        spec["repo"] = answer.strip()
    _write_job_file(job, spec)
    notify.notify(job, _drafted_message(job, spec))
    job.event("intake", repo=spec["repo"], title=spec.get("title"))
    status.set_status(job_dir, status.READY)
    return True


def _drafted_spec(job, request):
    """The job mapping Claude drafts from the request, or None. It is kept in `intake.json`, so a job that
    parked at the repository question does not pay for a second draft."""
    spec_file = job.path("intake.json")
    if os.path.exists(spec_file):
        return read_json(spec_file)
    try:
        repos = known_repos()
    except ValueError as exc:
        job.event("repos_unreadable", reason=str(exc)[:200])
        repos = {}                      # intake will ask the owner which repository it is
    reply, _ = claude(job, intake_prompt(request, repos), model="auto", max_turns=2, purpose="plan")
    spec = extract_yaml(reply)
    if spec is None:
        job.event("intake_failed", text=reply[:200])
        return None
    write_json(spec_file, spec)
    return spec


def _write_job_file(job, spec):
    front_matter = {
        "id": job.id,
        "title": spec.get("title", job.id),
        "repo": spec["repo"],
        "test": spec.get("test", DEFAULT_TEST_CMD),
        "branch": f"offload/{job.id}",
        "gates": spec.get("gates", []),
        "public": "false",
    }
    header = "\n".join(f"{key}: {json.dumps(value) if isinstance(value, list) else value}"
                       for key, value in front_matter.items())
    done_when = "\n".join(f"- {item.strip()}" for item in str(spec.get("done_when", "")).split("|") if item.strip())
    goal = str(spec.get("goal", "")).strip()
    write_text(job.path("job.md"), f"---\n{header}\n---\n## Goal\n{goal}\n\n## Done when\n{done_when}\n")


def _drafted_message(job, spec):
    """The owner-facing summary of a freshly drafted job: its title, goal, and done-when list."""
    title = spec.get("title", job.id)
    goal = str(spec.get("goal", "")).strip()
    done_when = "\n".join(f"- {item.strip()}" for item in str(spec.get("done_when", "")).split("|") if item.strip())
    return f"**[{job.id}] drafted**\ntitle: {title}\ngoal: {goal}\ndone when:\n{done_when}"
