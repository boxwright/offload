"""The pipeline for one job.

    clone -> plan (Claude) -> steps (local model; tests after each; Claude rescues a stalled step)
          -> review (Claude) -> one commit -> gate if public -> push -> report
"""
import hashlib
import os
import re

from offload.budget import job_cost, load_budget
from offload.config import CFG
from offload.files import write_text
from offload.jobs import Job
from offload.notify import ask_owner, notify
from offload.prompts import plan_prompt, rescue_prompt, review_fix_prompt, review_prompt, step_brief
from offload.report import diff_stat
from offload.results import is_approved, is_stuck, is_yes
from offload.sandbox import sh
from offload.workers import claude, local_harness, run_tests

EXIT_OK = 0
EXIT_SETUP = 2          # no clone, an empty clone, or no plan
EXIT_STEP = 3           # a step still fails after its rescue, or the rescues ran out
EXIT_REVIEW_FIXES = 4   # tests fail after the reviewer's changes
EXIT_NO_VERDICT = 5
EXIT_GATE = 6           # the owner declined, or did not answer
EXIT_PUSH = 7
EXIT_NO_CHANGE = 8      # the steps left nothing to commit
EXIT_EXCEPTION = 9

_STEP_LINE_RE = re.compile(r"\s*\d+[.)]")
_NOT_COMMITTED = [":(exclude)**/__pycache__/**", ":(exclude)*.pyc", ":(exclude).pytest_cache/**"]


def run(job_dir):
    """Run one job end to end. Returns an exit code; every failure is also a `fail` event with a reason."""
    job = Job(job_dir)
    job.event("start", repo=job.repo, branch=job.branch)
    base = _prepare_worktree(job)
    if base is None:
        return EXIT_SETUP
    plan_text, steps = _plan(job)
    if not steps:
        job.event("fail", reason="no plan steps")
        return EXIT_SETUP
    if not _execute_steps(job, steps, plan_text):
        return EXIT_STEP
    review_code = _review(job, plan_text)
    if review_code != EXIT_OK:
        return review_code
    return _commit_and_push(job, base)


def _prepare_worktree(job):
    """Clone the repository onto the job's branch. Returns the base commit, or None after a `fail` event."""
    if not os.path.isdir(job.work):
        code, _, err, _ = sh(["git", "clone", "-q", job.repo, job.work])
        if code != 0:
            job.event("fail", reason=f"git clone failed: {err.strip()[-200:]}")
            return None
        sh(["git", "checkout", "-q", "-b", job.branch], cwd=job.work)
        sh(["git", "config", "user.email", CFG.git_user_email], cwd=job.work)
        sh(["git", "config", "user.name", CFG.git_user_name], cwd=job.work)
    code, out, _, _ = sh(["git", "rev-parse", "--verify", "HEAD"], cwd=job.work)
    base = out.strip()
    if code != 0 or not base:
        job.event("fail", reason="the clone is empty (no commits on the default branch); check the repo's HEAD")
        return None
    write_text(job.path("base.txt"), base)
    job.event("worktree", path=job.work, base=base[:10])
    return base


def _plan(job):
    plan_text, _ = claude(job, plan_prompt(job), model="auto", max_turns=8, purpose="plan")
    steps = [line.strip() for line in plan_text.splitlines() if _STEP_LINE_RE.match(line)]
    if steps:
        write_text(job.plan, f"# Plan — {job.id}\n\n{plan_text}\n\n## Log\n")
        job.event("plan", steps=len(steps))
    return plan_text, steps


def _execute_steps(job, steps, plan_text):
    budget = load_budget()
    escalate_when = budget.get("escalate_when", {})
    max_fails = int(escalate_when.get("failed_test_iterations", CFG.max_test_fails))
    max_no_progress = int(escalate_when.get("no_progress_turns", 2))
    rescues_left = int(budget.get("claude", {}).get("per_job", {}).get("max_rescues", 2))
    for index, step in enumerate(steps, 1):
        ok, rescues_left, meta = _execute_step(job, index, step, plan_text, max_fails, max_no_progress, rescues_left)
        if not ok:
            return False
        with open(job.plan, "a") as plan_log:
            plan_log.write(f"- step {index} done by {meta['worker']} in {meta['wall_s']} s\n")
    return True


def _execute_step(job, index, step, plan_text, max_fails, max_no_progress, rescues_left):
    """The local model works the step until the tests pass. A stalled step gets one Claude rescue.

    Returns (ok, rescues left, the last local session's event fields).
    """
    feedback = ""
    fails = no_progress = 0
    last_diff = None
    while True:
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
        claude(job, rescue_prompt(job, step, text, test_output), model="auto", max_turns=15,
               purpose=f"rescue step {index}")
        passed, _ = run_tests(job)
        if not passed:
            job.event("fail", reason=f"step {index} still failing after rescue")
        return passed, rescues_left - 1, meta


def _review(job, plan_text):
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
    # Anything a worker committed is folded into the one commit the engine makes.
    sh(["git", "reset", "-q", "--soft", base], cwd=job.work)
    sh(["git", "add", "-A", "--", ".", *_NOT_COMMITTED], cwd=job.work)
    code, out, err, _ = sh(["git", "commit", "-q", "-m", f"offload: {job.title or job.id}"], cwd=job.work)
    if code != 0:
        job.event("fail", reason=f"nothing was committed: {(out + err).strip()[-160:] or 'no changes'}")
        return EXIT_NO_CHANGE
    change = diff_stat(job, base)
    if job.flag("public"):
        answer = ask_owner(job, "publish", f"Push branch `{job.branch}` to the PUBLIC remote `{job.repo}`? "
                                           f"Change: {change}")
        if not is_yes(answer):
            declined = "timeout" if answer is None else f"declined: {answer[:80]}"
            job.event("fail", reason=f"publish gate: {declined}")
            notify(job, f"[{job.id}] not pushed ({'no answer' if answer is None else 'declined'}). "
                        "Branch is ready in the worktree.")
            return EXIT_GATE
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    code, _, err, _ = sh(["git", "push", "-q", "-u", "origin", job.branch], cwd=job.work, timeout=300, env=env)
    job.event("push", ok=(code == 0), branch=job.branch, err=err[-200:])
    if code != 0:
        job.event("fail", reason=f"git push failed: {err.strip()[-200:]}")
        return EXIT_PUSH
    total, _ = job_cost(job.id)
    job.event("done")
    notify(job, f"[{job.id}] done: `{job.branch}` pushed. {change} · cost ${total:.2f} · "
                f"report: {job.path('REPORT.md')}")
    return EXIT_OK
