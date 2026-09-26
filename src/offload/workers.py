"""The two workers, and the test run that judges them.

`local_harness` is the local model: Claude Code's own harness in the sandbox, pointed at the
translation proxy. No subscription token enters that container. `claude` is the paid model, with the
budget pacer in front of it and rate-limit handling behind it.
"""
import datetime as dt
import os
import re
import time

from offload import progress, results, status
from offload.budget import budget_wait, ledger_add, model_for
from offload.clock import is_past
from offload.config import get_config
from offload.files import read_text, write_text
from offload.limits import MAX_LIMIT_WAITS, limit_kind, parse_reset, simulated_limit_message
from offload.prompts import RESUME_PROMPT
from offload.sandbox import claude_cmdline, run_sandbox, run_shell_in_sandbox, sh

LOCAL_EVENT = "local"
MAX_OVERLOADED_TRIES = 5
_SERVER_ERROR_RE = re.compile(r"\b503\b|Loading model|Connection error|overloaded")
_simulated_jobs = set()


def run_command(job, command):
    """Run one shell command in the job's worktree. Returns (exit code, stdout, stderr, wall seconds).

    On the host when `run_tests_on_host` is set (with `host_test_path` prepended to PATH); otherwise in a
    container with no network and no secrets, under the usual resource caps. A worker just wrote the code
    being run, so it never reaches the host unless the owner opts in.
    """
    config = get_config()
    if config.run_tests_on_host:
        path = f"{config.host_test_path}:{os.environ['PATH']}" if config.host_test_path else os.environ["PATH"]
        env = dict(os.environ, PATH=path)
        return sh(command, cwd=job.work, timeout=600, env=env)
    return run_shell_in_sandbox(command, job.work)


def run_tests(job):
    """Run the job's test command on the worktree. Returns (passed, the tail of the output).

    The command runs in a container with no network and no secrets, because it executes code a
    worker just wrote.
    """
    code, out, err, wall = run_command(job, job.test_cmd)
    lines = out.strip().splitlines()
    summary = lines[-1] if lines else err.strip()[-120:]
    job.event("tests", passed=(code == 0), summary=summary[:160], wall_s=wall)
    return code == 0, (out + err)[-3000:]


def local_harness(job, brief, purpose):
    """One fresh session of the local model on one brief. Returns (final answer, event fields)."""
    config = get_config()
    local_env = {
        "ANTHROPIC_BASE_URL": config.proxy_url,
        "ANTHROPIC_AUTH_TOKEN": "local",
        "ANTHROPIC_MODEL": config.local_model_name,
        "ANTHROPIC_SMALL_FAST_MODEL": config.local_model_name,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "OFFLOAD_ALLOW_HOSTS": "",                  # the local worker needs its own network only
    }
    inner = claude_cmdline(brief, config.local_model_name, config.local_tools, config.local_max_turns)
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


def claude(job, prompt, model, max_turns, purpose, tools=None):
    """One Claude call for a job: paced, retried when overloaded, parked at a rate limit.

    A call that a limit cut short is recorded as pending. The same call after the wake resumes that session.
    `tools` is the `--allowedTools` string; `None` uses the config's `claude_tools`.
    Returns (reply text, event fields).
    """
    _park_if_claude_is_blocked(job)
    budget_wait(job, purpose)
    if model == "auto":
        model = model_for(purpose)
    session_id = progress.pending_session(job, purpose)
    if session_id:
        job.event("resume", session=session_id)
        progress.save(job, pending=None)
        reply, wall = _resume_or_rerun(job, prompt, model, max_turns, session_id, tools)
    else:
        reply, wall = _call_claude(job, prompt, model, max_turns, tools=tools)
        reply = _maybe_simulate_limit(job, purpose, reply)
    overloaded_tries = 0
    while True:
        text = reply.get("result") or ""
        meta = _record_call(job, reply, wall, model, purpose)
        kind = results.classify(reply)
        if kind == results.OVERLOADED and overloaded_tries < MAX_OVERLOADED_TRIES:
            overloaded_tries += 1
            job.event("overloaded", try_=overloaded_tries)
            time.sleep(30 * overloaded_tries)
            reply, wall = _call_claude(job, prompt, model, max_turns, tools=tools)
        elif kind == results.LIMIT and _limit_parks(job) < MAX_LIMIT_WAITS:
            _park_for_limit(job, reply, purpose)
        else:
            return text, meta


def _call_claude(job, prompt, model, max_turns, resume=None, tools=None):
    """Run Claude Code once in the sandbox with the subscription token. Returns (reply, wall seconds).

    `tools` is the `--allowedTools` string; `None` uses the config's `claude_tools`.
    """
    claude_home = job.path("claude-home")           # sessions outlive the container, so --resume works
    os.makedirs(claude_home, exist_ok=True)
    workdir = job.work if os.path.isdir(job.work) else job.path("scratch")   # intake has no clone yet
    os.makedirs(workdir, exist_ok=True)
    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "OFFLOAD_ALLOW_HOSTS": get_config().claude_allow_hosts,
        "OFFLOAD_VERIFY_HOST": get_config().claude_allow_hosts.split()[0],
    }
    secret_env = claude_secret()
    mounts = [(workdir, "/workspace"), (claude_home, "/home/worker/.claude")]
    if tools is None:
        tools = get_config().claude_tools
    inner = claude_cmdline(prompt, model, tools, max_turns, resume=resume)
    reply, _, _, wall = run_sandbox(inner, env, mounts, secret_env=secret_env)
    return reply, wall


def claude_secret():
    """The one secret the paid worker's container receives, by `claude_auth`: the subscription token as
    CLAUDE_CODE_OAUTH_TOKEN, or an API key as ANTHROPIC_API_KEY. It goes through the process environment, never
    the command line."""
    config = get_config()
    if config.claude_auth == "api_key":
        return {"ANTHROPIC_API_KEY": _secret_file(config.api_key_file, "no Anthropic API key at {path}: save one "
                                                  "there (chmod 600), or set claude_auth: subscription")}
    if config.claude_auth == "subscription":
        return {"CLAUDE_CODE_OAUTH_TOKEN": _secret_file(config.token_file, "no Claude token at {path}: run "
                                                        "`claude setup-token` and save the token it prints to "
                                                        "that file (chmod 600)")}
    raise ValueError(f"unknown claude_auth {config.claude_auth!r}: allowed are subscription, api_key")


def _secret_file(path, missing):
    try:
        return read_text(path).strip()
    except FileNotFoundError:
        raise RuntimeError(missing.format(path=path)) from None


def _resume_or_rerun(job, prompt, model, max_turns, session_id, tools=None):
    """After a limit: continue the same session, or start over when that session cannot be found."""
    extra = {"tools": tools} if tools is not None else {}
    if not session_id:
        return _call_claude(job, prompt, model, max_turns, **extra)
    reply, wall = _call_claude(job, RESUME_PROMPT, model, max_turns, resume=session_id, **extra)
    if results.classify(reply) == results.SESSION_MISSING:
        job.event("resume_failed", reason="session not found; rerunning fresh")
        return _call_claude(job, prompt, model, max_turns, **extra)
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


def _blocked_until_file():
    """A provider limit belongs to the account, so one file beside the ledger holds it for every job."""
    return os.path.join(os.path.dirname(get_config().ledger), "claude-blocked-until")


def _park_if_claude_is_blocked(job):
    """Park without a call while a limit that another call met is still in force."""
    try:
        until = read_text(_blocked_until_file()).strip()
    except FileNotFoundError:
        return
    if not is_past(until):
        raise status.Parked(status.WAITING_LIMIT, until=until)


def _limit_parks(job):
    return int(progress.load(job).get("limit_parks", 0))


def _park_for_limit(job, reply, purpose):
    """Park the job until the provider's window reopens, plus half a minute. Record the session to resume."""
    text = reply.get("result") or ""
    local_now = dt.datetime.now().astimezone()
    reset = parse_reset(text) or (local_now + dt.timedelta(minutes=30))
    until = (reset + dt.timedelta(seconds=30)).isoformat()
    session_id = reply.get("session_id")
    job.event("limit", limit_kind=limit_kind(text), resets_at=reset.isoformat(),
              wait_s=int((reset - local_now).total_seconds()) + 30, session=session_id)
    progress.save(job, pending={"purpose": purpose, "session": session_id}, limit_parks=_limit_parks(job) + 1)
    os.makedirs(os.path.dirname(_blocked_until_file()), exist_ok=True)
    write_text(_blocked_until_file(), until + "\n")
    raise status.Parked(status.WAITING_LIMIT, until=until)


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
