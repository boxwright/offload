"""What the owner reads: a report per job, the status table, and the daily digest.

Everything here is assembled from the engine's own records (events and the ledger). No model writes it.
"""
import os
import re
import time
from collections import defaultdict

from offload import status
from offload.budget import job_costs, load_budget, pace_status
from offload.clock import TS_FMT, now
from offload.files import read_jsonl, read_text, write_text
from offload.jobs import job_dirs
from offload.notify import post
from offload.sandbox import sh

_TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)


def _by_kind(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("kind")].append(row)
    return grouped


def diff_stat(job, base):
    """The summary line of `git diff --stat` from the job's base commit, or an empty string."""
    lines = sh(["git", "diff", "--stat", base, "HEAD"], cwd=job.work)[1].strip().splitlines()
    return lines[-1] if lines else ""


def _outcome(exit_code, fails):
    if exit_code == 0:
        return "done"
    reason = fails[-1].get("reason", "") if fails else f"exit code {exit_code}"
    return f"failed ({reason})"


def write_report(job, exit_code):
    rows = list(read_jsonl(job.events))
    events = _by_kind(rows)
    total, per_model = job_costs().get(job.id, (0.0, {}))
    base_path = job.path("base.txt")
    change = diff_stat(job, read_text(base_path).strip()) if os.path.exists(base_path) else ""
    local_s = sum(row.get("wall_s", 0) for row in events["local"])
    claude_s = sum(row.get("wall_s", 0) for row in events["claude"])
    costs = ", ".join(f"{model} ${usd:.2f}" for model, usd in per_model.items())

    lines = [
        f"# Report — {job.id}: {job.title}", "",
        f"**Outcome:** {_outcome(exit_code, events['fail'])}  ",
        f"**Branch:** `{job.branch}` on `{job.repo}`  ",
        f"**Change:** {change}  ",
        f"**Cost (list-equivalent):** ${total:.2f} {costs}  ",
        f"**Time:** local worker {local_s:.0f} s over {len(events['local'])} sessions; "
        f"Claude {claude_s:.0f} s over {len(events['claude'])} calls  ",
        "", "## Decisions the engine made",
        *_decision_lines(events),
        "", "## Decisions the owner made",
        *([f"- {row.get('gate')}: {row.get('text')}" for row in events["answer"]] or ["- none needed"]),
        "", "## Steps",
        *[f"- {row.get('purpose')}: {row.get('worker')} {row.get('wall_s')} s, {row.get('turns')} turns"
          for row in rows if row.get("kind") in ("local", "claude")],
        "", f"Plan: `plan.md` · Events: `events.jsonl` · Generated {now()}",
    ]
    write_text(job.path("REPORT.md"), "\n".join(lines) + "\n")


def _plan_attempts(events):
    """How many times the planner was asked: the highest attempt number, or one for a clean first try."""
    return max((int(row.get("attempt") or 0) for row in events["plan_attempt"]), default=1)


def _decision_lines(events):
    planners = [row.get("worker", "?") for row in events["claude"] if row.get("purpose") == "plan"]
    attempts = _plan_attempts(events)
    lines = [f"- plan: {row.get('steps')} steps (planner {planners[0] if planners else '?'}, "
             f"{attempts} attempt{'s' if attempts > 1 else ''})" for row in events["plan"]]
    lines += [f"- plan attempt {row.get('attempt', '?')}: {row.get('reason') or 'first attempt'}"
              + (f", max_turns {row.get('max_turns')}" if row.get("max_turns") is not None else "")
              for row in events["plan_attempt"]]
    lines += [f"- escalated step {row.get('step')}: {row.get('reason')}" for row in events["escalate"]]
    lines += [f"- no progress on step {row.get('step')} after {row.get('turns')} identical attempts"
              for row in events["no_progress"]]
    if events["review"]:
        review = events["review"][-1]
        verdict = "APPROVE" if review.get("approved") else "REQUEST_CHANGES"
        notes = str(review.get("notes", ""))[:300].replace("\n", " ")
        lines.append(f"- review: {verdict} — {notes}")
    lines += [f"- limit ({row.get('limit_kind')}): parked until {row.get('resets_at')}, then resumed the session"
              for row in events["limit"]]
    lines += [f"- budget: parked {row.get('wait_s')} s (spent ${row.get('spent_usd')} vs pace ${row.get('pace_usd')})"
              for row in events["budget_wait"]]
    for row in events["parked"]:
        gate = f" ({row.get('gate')})" if row.get("gate") else ""
        lines.append(f"- parked at {row.get('t', '')[11:]}: {row.get('status')}{gate}")
    lines += [f"- continued at {row.get('t', '')[11:]} from the checkpoint: phase {row.get('phase')}, "
              f"step {row.get('step')}" for row in events["continue"]]
    return lines


def _last_event(job_dir):
    rows = list(read_jsonl(os.path.join(job_dir, "events.jsonl"), strict=False))
    if not rows:
        return ""
    return f"{rows[-1].get('t', '')[11:]} {rows[-1].get('kind')}"


def _title(job_dir):
    try:
        match = _TITLE_RE.search(read_text(os.path.join(job_dir, "job.md")))
    except FileNotFoundError:
        return ""
    return match.group(1)[:50] if match else ""


def status_table(jobs_root):
    costs = job_costs()
    rows = []
    for job_dir in job_dirs(jobs_root):
        job_id = os.path.basename(job_dir)
        state = status.job_status(job_dir).get("status", "?")
        total = costs.get(job_id, (0.0, {}))[0]
        rows.append(f"{job_id:<18} {state:<14} ${total:>6.2f}  {_last_event(job_dir):<22} {_title(job_dir)}")
    print("\n".join(rows) if rows else "no jobs")


def _recent_events(jobs_root, since):
    for job_dir in job_dirs(jobs_root, include_hidden=True):
        for row in read_jsonl(os.path.join(job_dir, "events.jsonl"), strict=False):
            try:
                stamp = time.mktime(time.strptime(row["t"], TS_FMT))
            except (KeyError, ValueError):
                continue
            if stamp >= since:
                yield row


def _open_gates(jobs_root):
    return [os.path.basename(job_dir) for job_dir in job_dirs(jobs_root, include_hidden=True)
            if status.job_status(job_dir).get("status") == status.WAITING_OWNER]


def digest(jobs_root, hours=24, send=True):
    """The daily summary: outcomes, Claude spend against pace, local sessions, limits, open gates."""
    events = _by_kind(_recent_events(jobs_root, time.time() - hours * 3600))
    done = sorted({row["job"] for row in events["done"]})
    failed = sorted({row["job"] for row in events["fail"]})
    pace = pace_status(load_budget())
    claude_usd = sum((row.get("usd") or 0) for row in events["claude"] if not row.get("simulated"))
    server_errors = sum(1 for row in events["local"] if (row.get("errors") or 0) > 0)
    plan_recoveries = sum(1 for row in events["plan_attempt"] if int(row.get("attempt") or 0) > 1)
    text = "\n".join([
        f"**offload digest — last {hours} h** ({now()})",
        f"jobs done: {', '.join(done) or 'none'} | failed: {', '.join(failed) or 'none'} | "
        f"gates open: {', '.join(_open_gates(jobs_root)) or 'none'}",
        f"claude: {len(events['claude'])} calls, ${claude_usd:.2f} list-equivalent | "
        f"week: ${pace.spent:.2f} spent of ${pace.allowance:.0f} allowance, "
        f"even pace ${pace.pace_now:.2f} → {'on pace' if pace.allowed else 'waiting'}",
        f"local model: {len(events['local'])} sessions, {server_errors} with server errors",
        f"limits hit: {len(events['limit'])} | escalations: {len(events['escalate'])} | "
        f"plan recoveries: {plan_recoveries} | budget waits: {len(events['budget_wait'])}",
    ])
    print(text)
    if send:
        post(text)
    return text
