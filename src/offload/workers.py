"""The two workers, and the test run that judges them.

`local_harness` is the local model: Claude Code's own harness in the sandbox, pointed at the
translation proxy. No subscription token enters that container. `claude` is the paid model, with the
budget pacer in front of it and rate-limit handling behind it.
"""
import datetime as dt
import os
import re
import time

from offload import results, status
from offload.budget import budget_wait, ledger_add, model_for
from offload.config import CFG
from offload.files import read_text
from offload.limits import MAX_LIMIT_WAITS, WAIT_CHUNK_S, limit_kind, parse_reset, simulated_limit_message
from offload.prompts import RESUME_PROMPT
from offload.sandbox import claude_cmdline, run_sandbox, run_shell_in_sandbox, sh

LOCAL_EVENT = "local"
MAX_OVERLOADED_TRIES = 5
_SERVER_ERROR_RE = re.compile(r"\b503\b|Loading model|Connection error|overloaded")
_simulated_jobs = set()


def run_tests(job):
    """Run the job's test command on the worktree. Returns (passed, the tail of the output).

    The command runs in a container with no network and no secrets, because it executes code a
    worker just wrote.
    """
    if CFG.run_tests_on_host:
        path = f"{CFG.host_test_path}:{os.environ['PATH']}" if CFG.host_test_path else os.environ["PATH"]
        env = dict(os.environ, PATH=path)
        code, out, err, wall = sh(job.test_cmd, cwd=job.work, timeout=600, env=env)
    else:
        code, out, err, wall = run_shell_in_sandbox(job.test_cmd, job.work)
    lines = out.strip().splitlines()
    summary = lines[-1] if lines else err.strip()[-120:]
    job.event("tests", passed=(code == 0), summary=summary[:160], wall_s=wall)
    return code == 0, (out + err)[-3000:]


def local_harness(job, brief, purpose):
    """One fresh session of the local model on one brief. Returns (final answer, event fields)."""
    local_env = {
        "ANTHROPIC_BASE_URL": CFG.proxy_url,
        "ANTHROPIC_AUTH_TOKEN": "local",
        "ANTHROPIC_MODEL": CFG.local_model_name,
        "ANTHROPIC_SMALL_FAST_MODEL": CFG.local_model_name,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "OFFLOAD_ALLOW_HOSTS": "",                  # the local worker needs its own network only
    }
    inner = claude_cmdline(brief, CFG.local_model_name, CFG.local_tools, CFG.local_max_turns)
    reply, code, err, wall = run_sandbox(inner, local_env, [(job.work, "/workspace")])
    text = reply.get("result") or ""
    meta = {
        "worker": "local/harness", "purpose": purpose, "wall_s": wall, "exit": code,
        "turns": reply.get("num_turns"), "is_error": reply.get("is_error"),
        "terminal_reason": reply.get("terminal_reason"), "session": reply.get("session_id"),
        "errors": len(_SERVER_ERROR_RE.findall(text + err)),
    }
    job.event(LOCAL_EVENT, **meta, text=text[-300:])
    return text, meta


def claude(job, prompt, model, max_turns, purpose):
    """One Claude call for a job, paced, retried when overloaded, resumed after a rate limit.

    Returns (reply text, event fields).
    """
    budget_wait(job, purpose)
    if model == "auto":
        model = model_for(purpose)
    reply, wall = _call_claude(job, prompt, model, max_turns)
    reply = _maybe_simulate_limit(job, purpose, reply)
    limit_waits = overloaded_tries = 0
    while True:
        text = reply.get("result") or ""
        meta = _record_call(job, reply, wall, model, purpose)
        kind = results.classify(reply)
        if kind == results.OVERLOADED and overloaded_tries < MAX_OVERLOADED_TRIES:
            overloaded_tries += 1
            job.event("overloaded", try_=overloaded_tries)
            time.sleep(30 * overloaded_tries)
            reply, wall = _call_claude(job, prompt, model, max_turns)
        elif kind == results.LIMIT and limit_waits < MAX_LIMIT_WAITS:
            limit_waits += 1
            _wait_for_limit(job, reply)
            reply, wall = _resume_or_rerun(job, prompt, model, max_turns, reply.get("session_id"))
        else:
            return text, meta


def _call_claude(job, prompt, model, max_turns, resume=None):
    """Run Claude Code once in the sandbox with the subscription token. Returns (reply, wall seconds)."""
    claude_home = job.path("claude-home")           # sessions outlive the container, so --resume works
    os.makedirs(claude_home, exist_ok=True)
    workdir = job.work if os.path.isdir(job.work) else job.path("scratch")   # intake has no clone yet
    os.makedirs(workdir, exist_ok=True)
    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "OFFLOAD_ALLOW_HOSTS": CFG.claude_allow_hosts,
        "OFFLOAD_VERIFY_HOST": CFG.claude_allow_hosts.split()[0],
    }
    secret_env = {"CLAUDE_CODE_OAUTH_TOKEN": _subscription_token()}
    mounts = [(workdir, "/workspace"), (claude_home, "/home/worker/.claude")]
    inner = claude_cmdline(prompt, model, CFG.claude_tools, max_turns, resume=resume)
    reply, _, _, wall = run_sandbox(inner, env, mounts, secret_env=secret_env)
    return reply, wall


def _subscription_token():
    try:
        return read_text(CFG.token_file).strip()
    except FileNotFoundError:
        raise RuntimeError(f"no Claude token at {CFG.token_file}: run `claude setup-token` and save "
                           "the token it prints to that file (chmod 600)") from None


def _resume_or_rerun(job, prompt, model, max_turns, session_id):
    """After a limit: continue the same session, or start over when that session cannot be found."""
    if not session_id:
        return _call_claude(job, prompt, model, max_turns)
    reply, wall = _call_claude(job, RESUME_PROMPT, model, max_turns, resume=session_id)
    if results.classify(reply) == results.SESSION_MISSING:
        job.event("resume_failed", reason="session not found; rerunning fresh")
        return _call_claude(job, prompt, model, max_turns)
    return reply, wall


def _record_call(job, reply, wall, model, purpose):
    """Write the call to the ledger and the job's events. Returns the event fields."""
    usage = reply.get("usage") or {}
    simulated = bool(reply.get("simulated"))
    if not simulated:
        ledger_add(job, model, purpose, reply.get("total_cost_usd"),
                   usage.get("cache_read_input_tokens"), usage.get("output_tokens"))
    meta = {
        "worker": f"claude/{model}", "purpose": purpose, "wall_s": wall, "is_error": reply.get("is_error"),
        "terminal_reason": reply.get("terminal_reason"), "turns": reply.get("num_turns"),
        "usd": reply.get("total_cost_usd"), "cache_read": usage.get("cache_read_input_tokens"),
        "output_tokens": usage.get("output_tokens"), "session": reply.get("session_id"),
    }
    job.event("claude", **meta, simulated=simulated, text=(reply.get("result") or "")[:300])
    return meta


def _wait_for_limit(job, reply):
    """Sleep until the provider's window reopens, plus half a minute."""
    text = reply.get("result") or ""
    local_now = dt.datetime.now().astimezone()
    reset = parse_reset(text) or (local_now + dt.timedelta(minutes=30))
    until = reset + dt.timedelta(seconds=30)
    session_id = reply.get("session_id")
    job.event("limit", limit_kind=limit_kind(text), resets_at=reset.isoformat(),
              wait_s=int((until - local_now).total_seconds()), session=session_id)
    status.set_status(job.dir, status.WAITING_LIMIT, until=until.isoformat())
    while True:
        remaining = (until - dt.datetime.now().astimezone()).total_seconds()
        if remaining <= 0:
            break
        time.sleep(min(remaining, WAIT_CHUNK_S))
        if remaining > WAIT_CHUNK_S:
            job.event("waiting", remaining_s=int(remaining - WAIT_CHUNK_S))
    job.event("resume", session=session_id)
    status.set_status(job.dir, status.RUNNING)


def _maybe_simulate_limit(job, purpose, reply):
    """Test switch: with ENGINE_SIMULATE_LIMIT=1, a job's first review call is answered as a session limit.

    The real call has already run, so its session id is real and the resume path is exercised for real.
    """
    if os.environ.get("ENGINE_SIMULATE_LIMIT") != "1" or purpose != "review" or job.id in _simulated_jobs:
        return reply
    _simulated_jobs.add(job.id)
    minutes = int(os.environ.get("ENGINE_SIMULATE_LIMIT_MINUTES", "3"))
    return {"is_error": True, "result": simulated_limit_message(minutes),
            "session_id": reply.get("session_id"), "simulated": True}
