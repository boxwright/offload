"""Intake: turn a one-line idea into a full job file, asking the owner only when the repository is unclear."""
import json
import re

import yaml

from offload import status
from offload.files import write_text
from offload.jobs import DEFAULT_TEST_CMD, Job, known_repos
from offload.notify import ask_owner
from offload.prompts import intake_prompt
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
    reply, _ = claude(job, intake_prompt(request, known_repos()), model="auto", max_turns=2, purpose="plan")
    spec = extract_yaml(reply)
    if spec is None:
        job.event("intake_failed", text=reply[:200])
        status.set_status(job_dir, status.FAILED, reason="intake parse")
        return False
    if str(spec.get("repo", "UNKNOWN")).upper() == "UNKNOWN":
        answer = ask_owner(job, "intake", f"Which repository is `{request[:120]}` about? "
                                          "Reply with a path or git URL, or `skip`.")
        if not answer or answer.strip().lower() == "skip":
            status.set_status(job_dir, status.FAILED, reason="no repo")
            return False
        spec["repo"] = answer.strip()
    _write_job_file(job, spec)
    job.event("intake", repo=spec["repo"], title=spec.get("title"))
    status.set_status(job_dir, status.READY)
    return True


def _write_job_file(job, spec):
    front_matter = {
        "id": job.id,
        "title": spec.get("title", job.id),
        "repo": spec["repo"],
        "test": spec.get("test", DEFAULT_TEST_CMD),
        "branch": f"offload/{job.id}",
        "tier": spec.get("tier", "local"),
        "gates": spec.get("gates", []),
        "public": "false",
    }
    header = "\n".join(f"{key}: {json.dumps(value) if isinstance(value, list) else value}"
                       for key, value in front_matter.items())
    done_when = "\n".join(f"- {item.strip()}" for item in str(spec.get("done_when", "")).split("|") if item.strip())
    goal = str(spec.get("goal", "")).strip()
    write_text(job.path("job.md"), f"---\n{header}\n---\n## Goal\n{goal}\n\n## Done when\n{done_when}\n")
