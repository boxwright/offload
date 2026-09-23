"""Every prompt the engine sends to a worker. Pure functions of a job and some text."""
import json
import textwrap

RESUME_PROMPT = "Continue exactly where you left off and finish your reply."

_NO_TEST_EDITS = "Do not change existing test files; you may add new test files when the job asks for tests."
_TEST_EDITS_ALLOWED = ("You may update existing test files only as far as the refactor requires "
                       "(imports, fixtures, names); never delete a test's assertions to make it pass.")
RULES = (
    "Rules: work only inside this directory. {tests} "
    "Do not run git commit, git push, sudo, ssh, docker, or network installs; the engine commits. "
    "Run the tests with `{test}`. Stop when your step is done. If you cannot finish the step, make the "
    "first line of your final answer exactly `STUCK — <reason>`; otherwise do not write the word STUCK at all."
)


def rules_for(job):
    """The standing rules. A refactoring job sets `allow_test_edits: true` to be allowed to update tests."""
    tests = _TEST_EDITS_ALLOWED if job.flag("allow_test_edits") else _NO_TEST_EDITS
    return RULES.format(tests=tests, test=job.test_cmd)


def plan_prompt(job):
    return textwrap.dedent(f"""\
    You are the planner. Read this repository (read-only) and write a plan for the job below.
    Output ONLY a markdown list of 2-6 numbered steps, each one line, each ending with a tag in parentheses: (local-ok) for a step a capable local model can do alone, or (hard) for a step that needs strong reasoning. Then one line `Test: <command>`.
    Do not include steps for committing, pushing, opening a PR, or reviewing: the engine does those itself after the steps.
    Order the steps so that the tests pass after every step, because the engine runs them after each one. A step that removes or renames something must update every user of it in the same step, or an earlier step must add the new name while the old one still works.
    Every step must change files. Do not write a step that only reads, investigates, verifies or runs tests: the tests run after every step, and a step that changes nothing counts as a stall. Fold any reading into the step that makes the change.
    Job title: {job.title}
    Job goal and done-when:
    {job.body.strip()}
    """)


def step_brief(job, step, plan_text, feedback=""):
    previous = f"\nPrevious attempt feedback:\n{feedback}\n" if feedback else ""
    return (f"You are the executor for one step of a job in this repository.\n"
            f"Job: {job.title}\nPlan:\n{plan_text}\n\nYour step now: {step}\n{previous}\n{rules_for(job)}")


def rescue_prompt(job, step, last_message, test_output):
    return (f"Rescue: the local executor could not finish this step.\nStep: {step}\n"
            f"Its last message: {last_message[-800:]}\nTest output:\n{test_output[-1500:]}\n"
            f"Fix it so the tests pass. {rules_for(job)}")


def review_prompt(job, plan_text):
    return textwrap.dedent(f"""\
    You are the reviewer. The job below was executed by another worker on this repository; the changes are the uncommitted diff (run `git diff` and `git status`; read files as needed; you may run the tests with `{job.test_cmd}`).
    Job: {job.title}
    Done-when: {job.body.strip()}
    Plan that was followed:
    {plan_text}
    Judge only the code change against the goal. The engine commits and pushes AFTER your verdict, so an uncommitted diff is expected and untracked cache directories are ignored. Be brief: read the diff, run the tests once, read at most three files. Then reply. Your reply must start with exactly one word on its own line: APPROVE or REQUEST_CHANGES. Then up to five lines of specific notes.
    """)


def review_fix_prompt(job, verdict):
    return f"The reviewer asked for changes. Apply them.\nReviewer notes:\n{verdict}\n{rules_for(job)}"


def intake_prompt(request, repos):
    return textwrap.dedent(f"""\
    You are the intake planner for an unattended engineering engine. Turn this one-line request into a job file.
    Request: {request}
    Known repositories (path → purpose): {json.dumps(repos)}
    Reply with ONLY a YAML block with keys: title (one line), repo (one of the known repository paths, or the word UNKNOWN), test (shell command to run the tests, or "none"), goal (2-4 sentences), done_when (2-4 checkable bullets, one per line, joined with ' | '), gates (list from money, publish, delete that this job could need).
    """)
