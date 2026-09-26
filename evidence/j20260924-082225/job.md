---
title: Run the spec checks before a job may report done
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
id: j20260924-082225
branch: offload/j20260924-082225
---
## Goal
A spec Done-when list is prose the models read, not a gate the engine enforces.
Job j20260924-062008 stated "git diff --name-only main lists only netmon.py and
tests/test_netmon_srcfail.py", shipped four files, and both the engine and the
reviewer reported done. Nobody was misled because a human read the diff. At one
job a day that works; with many agents running, nobody reads every diff and done
is the signal people trust.

Do not try to interpret the English bullets. Add an explicit, optional list of
shell commands the engine runs and requires to pass, so the spec author decides
what is machine-checkable and the engine decides nothing.

Requirements:
1. Job front matter gains an optional `checks:` key holding a list of strings,
   each a shell command. A spec without `checks` behaves exactly as today.
2. `src/offload/jobs.py`: parse `checks` into `Job.checks`, defaulting to an
   empty list. A `checks` value that is not a list of strings is a job error with
   a message naming the key.
3. The engine runs the checks after the review step and before the job is marked
   done, in the job worktree, with the same environment and working directory the
   test command uses. Each check runs once. A check that exits non-zero fails.
4. A failed check makes the job outcome `failed` with reason `checks`, and the
   branch is still pushed so the work can be inspected. The engine does not try
   to fix a failed check and does not call Claude again for it.
5. Every check is recorded as its own event with the command, its exit code, and
   the first 500 characters of its combined output.
6. `REPORT.md` gains a `## Checks` section listing each command with `pass` or
   `fail` and, for a failure, that captured output. When a job has no checks the
   section is omitted entirely.
7. Checks run with no network, exactly as the project tests do, and are subject
   to the existing per-worker resource limits.
8. Tests in `tests/`: a job with no `checks` is unchanged; a job whose checks all
   pass reports done; a job with one failing check reports failed with reason
   `checks` and still pushes the branch; the report renders both outcomes; a
   malformed `checks` value is rejected with a clear message.

## Done when
- `python3 -m pytest -q tests` passes
- `grep -rn "checks" src/offload/jobs.py src/offload/report.py` shows the new key handled in both
- A spec with no `checks` key produces a report with no Checks section
