"""Telling the owner things: a Discord webhook, and the gate that waits for an answer."""
import json
import os
import time
import urllib.error
import urllib.request

from offload import status
from offload.config import CFG
from offload.files import read_text, remove_if_exists, write_text

GATE_POLL_S = 10


def post_webhook(text):
    """Post one message. Returns (ok, detail) and never raises."""
    try:
        url = read_text(CFG.webhook_file).strip()
    except FileNotFoundError:
        return False, "no webhook file"
    body = json.dumps({"content": text[:1900], "username": "offload"}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "User-Agent": "offload/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return True, response.status
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return False, str(exc)[:120]


def notify(job, text):
    """Post a message about a job and record the outcome in the job's events."""
    ok, detail = post_webhook(text)
    if ok:
        job.event("notify", ok=True, http=detail, text=text[:120])
    else:
        job.event("notify", ok=False, reason=detail)
    return ok


def ask_owner(job, gate, question):
    """Stop at a gate: write the question, tell the owner, wait for `offload answer`.

    Returns the answer text, or None when nobody answered within `gate_wait_s`.
    """
    answer_path = job.path("answer.txt")
    remove_if_exists(answer_path)
    reply_with = f'offload answer {job.dir} "<text>"'
    write_text(job.path("question.md"), f"# Gate: {gate}\n\n{question}\n\nAnswer with: {reply_with}\n")
    job.event("gate", gate=gate, question=question[:200])
    status.set_status(job.dir, status.WAITING_OWNER, gate=gate)
    notify(job, f"**[{job.id}] gate: {gate}**\n{question}\n"
                f"Reply on the engine host: `offload answer {job.dir} \"yes\"` (or no, or your own text)")
    deadline = time.time() + CFG.gate_wait_s
    while time.time() < deadline:
        if os.path.exists(answer_path):
            answer = read_text(answer_path).strip()
            job.event("answer", gate=gate, text=answer[:200])
            status.set_status(job.dir, status.RUNNING)
            return answer
        time.sleep(GATE_POLL_S)
    job.event("gate_timeout", gate=gate)
    return None
