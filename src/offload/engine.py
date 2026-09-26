"""The pipeline for one job.

    clone -> plan (Claude) -> steps (local model; tests after each; Claude rescues a stalled step)
          -> review (Claude) -> one commit -> gate if public -> push -> checks -> report

Each finished phase is written to the job's checkpoint (`progress`). A job that was parked at a wait, or
interrupted by a restart, runs again through `run` and skips what the checkpoint says is finished.
"""
import hashlib
import os
import re
import shutil

from offload import progress
from offload.budget import job_cost, load_budget, plan_attempts
from offload.clock import now
from offload.config import get_config, plan_tools
from offload.files import read_text, write_text
from offload.jobs import Job
from offload.notify import ask_owner, notify
from offload.prompts import plan_prompt, plan_retry_prompt, rescue_prompt, review_fix_prompt, review_prompt, step_brief
from offload.report import diff_stat
from offload.results import is_approved, is_stuck, is_yes
from offload.sandbox import sh
from offload.workers import claude, local_harness, run_command, run_tests

EXIT_OK = 0
EXIT_SETUP = 2          # no clone, an empty clone, or no plan
EXIT_STEP = 3           # a step still fails after its rescue, or the rescues ran out
EXIT_REVIEW_FIXES = 4   # tests fail after the reviewer's changes
EXIT_NO_VERDICT = 5
EXIT_GATE = 6           # the owner declined, or did not answer
EXIT_PUSH = 7
EXIT_NO_CHANGE = 8      # the steps left nothing to commit
EXIT_EXCEPTION = 9
EXIT_CANCELLED = 11
EXIT_PARKED = 10        # `offload run` only: the job waits; run it again when the wait is over
EXIT_CHECKS = 12        # a spec check exited non-zero after the push

_STEP_LINE_RE = re.compile(r"\s*\d+[.)]")
_NOT_COMMITTED = [":(exclude)**/__pycache__/**", ":(exclude)*.pyc", ":(exclude).pytest_cache/**"]


class Cancelled(Exception):
    """The owner cancelled the job (`offload cancel`). Checked before every worker call."""


def _stop_if_cancelled(job):
    if os.path.exists(job.path("cancel")):
        raise Cancelled()


def run(job_dir):
    """Run one job. See `_run`. A cancelled job ends with a `fail` event and EXIT_CANCELLED."""
    try:
        return _run(job_dir)
    except Cancelled:
        Job(job_dir).event("fail", reason="cancelled by the owner")
        return EXIT_CANCELLED


def _confirm_gate(job):
    """Gate a `--confirm` job on the owner's approval, before the worktree is prepared.

    The first call asks the owner and parks the job in WAITING_OWNER. The call after the wake returns the
    answer: an approval is recorded in `confirmed` and lets the job continue; a decline or a timeout fails
    with EXIT_GATE. A job without the flag, or one already approved, runs straight on.
    """
    if not job.flag("confirm") or os.path.exists(job.path("confirmed")):
        return True
    answer = ask_owner(job, "confirm", f"Run job `{job.id}`: {job.title or job.id}? Reply `yes` to start it.")
    if not is_yes(answer):
        declined = "timeout" if answer is None else f"declined: {answer[:80]}"
        job.event("fail", reason=f"confirm gate: {declined}")
        notify(job, f"[{job.id}] not run ({'no answer' if answer is None else 'declined'}).")
        return False
    write_text(job.path("confirmed"), now() + "\n")
    return True


def _run(job_dir):
    """Run one job to its end, or to its next wait (`status.Parked` passes through to the caller).

    Returns an exit code; every failure is also a `fail` event with a reason.
    """
    job = Job(job_dir)
    if not _confirm_gate(job):
        return EXIT_GATE
    checkpoint = progress.load(job)
    if checkpoint.get("phase") == progress.PLAN:
        job.event("start", repo=job.repo, branch=job.branch)
    else:
        job.event("continue", phase=checkpoint.get("phase"), step=checkpoint.get("step"))
    base = _prepare_worktree(job)
    if base is None:
        return EXIT_SETUP
    _stop_if_cancelled(job)
    plan_text, steps = _plan(job)
    if not steps:
        job.event("fail", reason="no plan steps")
        return EXIT_SETUP
    if not _execute_steps(job, steps, plan_text):
        return EXIT_STEP
    if progress.still_to_run(progress.load(job), progress.REVIEW):
        review_code = _review(job, plan_text)
        if review_code != EXIT_OK:
            return review_code
        progress.save(job, phase=progress.COMMIT)
    return _commit_and_push(job, base)


def _prepare_worktree(job):
    """Clone the repository onto the job's branch. Returns the base commit, or None after a `fail` event.

    A clone with a recorded base is kept: it holds the work so far. A clone without one was cut short,
    and is made again.
    """
    base_file = job.path("base.txt")
    if os.path.isdir(job.work) and os.path.exists(base_file):
        return read_text(base_file).strip()
    shutil.rmtree(job.work, ignore_errors=True)
    code, _, err, _ = sh(["git", "clone", "-q", job.repo, job.work])
    if code != 0:
        job.event("fail", reason=f"git clone failed: {err.strip()[-200:]}")
        return None
    sh(["git", "checkout", "-q", "-b", job.branch], cwd=job.work)
    sh(["git", "config", "user.email", get_config().git_user_email], cwd=job.work)
    sh(["git", "config", "user.name", get_config().git_user_name], cwd=job.work)
    code, out, _, _ = sh(["git", "rev-parse", "--verify", "HEAD"], cwd=job.work)
    base = out.strip()
    if code != 0 or not base:
        job.event("fail", reason="the clone is empty (no commits on the default branch); check the repo's HEAD")
        return None
    write_text(base_file, base)
    job.event("worktree", path=job.work, base=base[:10])
    return base


_PLAN_RETRY_EXTRA_TURNS = 10     # a retry gets this many turns more than `plan_max_turns`


def _plan(job):
    """The plan text and its steps. The planner runs once per job; a job that continues reads `plan.txt`.

    A plan that comes back empty is not a dead end: the ladder re-asks, escalating the turn budget and
    then narrowing the prompt, until `plan_attempts()` attempts are spent.
    `plan_reads: index` hands the planner the `git ls-files` file tree instead of letting it read the repo.
    """
    plan_file = job.path("plan.txt")
    if os.path.exists(plan_file):
        plan_text = read_text(plan_file)
        return plan_text, _steps_of(plan_text)
    config = get_config()
    tree = _file_tree(job.work) if config.plan_reads == "index" else None
    attempts = plan_attempts()
    plan_text, meta = "", {}
    for attempt in range(1, attempts + 1):
        prompt, max_turns = _plan_call(job, attempt, config, tree)
        job.event("plan_attempt", attempt=attempt, reason=_plan_reason(attempt, meta), max_turns=max_turns)
        plan_text, meta = claude(job, prompt, model="auto", max_turns=max_turns, purpose="plan",
                                 tools=plan_tools(config))
        if _steps_of(plan_text) and not _ended_on_max_turns(meta):
            break
    steps = _steps_of(plan_text)
    if steps:
        write_text(plan_file, plan_text)
        write_text(job.plan, f"# Plan — {job.id}\n\n{plan_text}\n\n## Log\n")
        job.event("plan", steps=len(steps))
        rescues = int(load_budget().get("claude", {}).get("per_job", {}).get("max_rescues", 2))
        progress.save(job, phase=progress.STEPS, step=1, rescues_left=rescues)
    return plan_text, steps


def _plan_call(job, attempt, config, tree):
    """The prompt and turn budget for a plan attempt: the first is the full ask with `plan_max_turns`, the
    first retry gets ten more turns, and the narrowed re-ask takes over from the second retry on."""
    if attempt == 1:
        return plan_prompt(job, tree), config.plan_max_turns
    if attempt == 2:
        return plan_prompt(job, tree), config.plan_max_turns + _PLAN_RETRY_EXTRA_TURNS
    return plan_retry_prompt(job), config.plan_max_turns + _PLAN_RETRY_EXTRA_TURNS


def _plan_reason(attempt, meta):
    """Why the ladder is asking again: the previous attempt's failure, or the first attempt."""
    if attempt == 1:
        return "first attempt"
    if _ended_on_max_turns(meta):
        return "previous attempt ended on max_turns"
    return "previous attempt had no steps"


def _ended_on_max_turns(meta):
    """Whether the worker's own record says the run stopped at its turn budget."""
    return meta.get("terminal_reason") == "max_turns"


def _file_tree(work):
    """The worktree's `git ls-files` file tree, one path per line, for the index-mode planner."""
    code, out, _, _ = sh(["git", "ls-files"], cwd=work)
    return out.strip() if code == 0 else ""


def _steps_of(plan_text):
    return [line.strip() for line in plan_text.splitlines() if _STEP_LINE_RE.match(line)]


def _execute_steps(job, steps, plan_text):
    budget = load_budget()
    escalate_when = budget.get("escalate_when", {})
    max_fails = int(escalate_when.get("failed_test_iterations", get_config().max_test_fails))
    max_no_progress = int(escalate_when.get("no_progress_turns", 2))
    checkpoint = progress.load(job)
    if not progress.still_to_run(checkpoint, progress.STEPS):
        return True
    rescues_left = int(checkpoint.get("rescues_left", 2))
    for index, step in enumerate(steps, 1):
        if index < int(checkpoint.get("step", 1)):
            continue
        ok, rescues_left, meta = _execute_step(job, index, step, plan_text, max_fails, max_no_progress, rescues_left)
        if not ok:
            return False
        with open(job.plan, "a") as plan_log:
            plan_log.write(f"- step {index} done by {meta['worker']} in {meta['wall_s']} s\n")
        progress.save(job, step=index + 1, rescues_left=rescues_left)
    progress.save(job, phase=progress.REVIEW)
    return True


def _execute_step(job, index, step, plan_text, max_fails, max_no_progress, rescues_left):
    """The local model works the step until the tests pass. A stalled step gets one Claude rescue.

    Returns (ok, rescues left, the last local session's event fields).
    """
    feedback = ""
    fails = no_progress = 0
    last_diff = None
    while True:
        _stop_if_cancelled(job)
        text, meta = local_harness(job, step_brief(job, step, plan_text, feedback), purpose=f"step {index}")
        passed, test_output = run_tests(job)
        stuck = is_stuck(text)
        if passed:
            if stuck:
                job.event("stuck_but_green", step=index, text=text[:200])
            return True, rescues_left, meta
        fails += 1
        diff = hashlib.sha1(sh(["git", "diff"], cwd=job.work)[1].encode()).hexdigest()
        no_progress = no_progress + 1 if diff == last_diff else 0
        last_diff = diff
        stalled = no_progress >= max_no_progress
        if stalled:
            job.event("no_progress", step=index, turns=no_progress)
        if not (stuck or stalled or fails >= max_fails):
            feedback = f"Tests still fail after your change. Output:\n{test_output[-1500:]}"
            continue
        if rescues_left <= 0:
            job.event("fail", reason=f"step {index}: no rescues left")
            return False, rescues_left, meta
        reason = "stuck" if stuck else "no progress" if stalled else f"{fails} test failures"
        job.event("escalate", step=index, reason=reason)
        _stop_if_cancelled(job)
        claude(job, rescue_prompt(job, step, text, test_output), model="auto", max_turns=15,
               purpose=f"rescue step {index}")
        passed, _ = run_tests(job)
        if not passed:
            job.event("fail", reason=f"step {index} still failing after rescue")
        return passed, rescues_left - 1, meta


def _review(job, plan_text):
    _stop_if_cancelled(job)
    verdict, meta = claude(job, review_prompt(job, plan_text), model="auto", max_turns=25, purpose="review")
    if not verdict.strip() or meta.get("is_error"):
        job.event("review_inconclusive", terminal_reason=meta.get("terminal_reason"), is_error=meta.get("is_error"))
        verdict, meta = claude(job, review_prompt(job, plan_text), model="auto", max_turns=40,
                               purpose="review retry")
        if not verdict.strip() or meta.get("is_error"):
            job.event("fail", reason="no review verdict twice")
            return EXIT_NO_VERDICT
    approved = is_approved(verdict)
    job.event("review", approved=approved, notes=verdict[:400])
    if approved:
        return EXIT_OK
    local_harness(job, review_fix_prompt(job, verdict), purpose="review fixes")
    passed, _ = run_tests(job)
    if not passed:
        job.event("fail", reason="tests failing after review fixes")
        return EXIT_REVIEW_FIXES
    return EXIT_OK


def _commit_and_push(job, base):
    if progress.still_to_run(progress.load(job), progress.COMMIT):
        # Anything a worker committed is folded into the one commit the engine makes.
        sh(["git", "reset", "-q", "--soft", base], cwd=job.work)
        sh(["git", "add", "-A", "--", ".", *_NOT_COMMITTED], cwd=job.work)
        code, out, err, _ = sh(["git", "commit", "-q", "-m", f"offload: {job.title or job.id}"], cwd=job.work)
        if code != 0:
            job.event("fail", reason=f"nothing was committed: {(out + err).strip()[-160:] or 'no changes'}")
            return EXIT_NO_CHANGE
        progress.save(job, phase=progress.GATE)
    change = diff_stat(job, base)
    if job.flag("public") and progress.still_to_run(progress.load(job), progress.GATE):
        answer = ask_owner(job, "publish", f"Push branch `{job.branch}` to the PUBLIC remote `{job.repo}`? "
                                           f"Change: {change}")
        if not is_yes(answer):
            declined = "timeout" if answer is None else f"declined: {answer[:80]}"
            job.event("fail", reason=f"publish gate: {declined}")
            notify(job, f"[{job.id}] not pushed ({'no answer' if answer is None else 'declined'}). "
                        "Branch is ready in the worktree.")
            return EXIT_GATE
    progress.save(job, phase=progress.PUSH)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    code, _, err, _ = sh(["git", "push", "-q", "-u", "origin", job.branch], cwd=job.work, timeout=300, env=env)
    job.event("push", ok=(code == 0), branch=job.branch, err=err[-200:])
    if code != 0:
        job.event("fail", reason=f"git push failed: {err.strip()[-200:]}")
        return EXIT_PUSH
    checks_code = _run_checks(job)
    if checks_code != EXIT_OK:
        return checks_code
    total, _ = job_cost(job.id)
    job.event("done")
    notify(job, f"[{job.id}] done: `{job.branch}` pushed. {change} · cost ${total:.2f} · "
                f"report: {job.path('REPORT.md')}")
    return EXIT_OK


def _run_checks(job):
    """The job's spec checks, once each, after the push. One `check` event per command.

    When any check exits non-zero the job fails with reason `checks` and the function returns
    EXIT_CHECKS: the branch is already out, so there is no Claude call and no retry.
    """
    failed = []
    for command in job.checks:
        code, out, err, _ = run_command(job, command)
        job.event("check", command=command, exit=code, output=(out + err)[:500])
        if code != 0:
            failed.append(command)
    if failed:
        job.event("fail", reason=f"checks: {', '.join(failed)}")
        return EXIT_CHECKS
    return EXIT_OK
