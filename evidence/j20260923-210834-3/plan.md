# Plan — j20260923-210834-3

1. In `src/offload/intake.py`, after `_write_job_file` succeeds, post the drafted title, goal and done-when through `notify.notify` (never `ask_owner`, no new `Parked`) and add a test in `tests/test_intake_and_queue.py` asserting the message is posted and the job lands in `status.READY` with no gate/deadline. (local-ok)
2. In `src/offload/jobs.py`, extend `add(jobs_root, text, spec_file=None, confirm=False)` so a `job.md`-style spec file is parsed (front matter plus `## Goal` / `## Done when`) and copied into the new job's `job.md` with `id`/`branch`/`test` defaults filled in and status set to `status.READY` (so intake's Claude call is skipped), while `confirm=True` writes `confirm: true` into the front matter on both paths; cover the parsing and both statuses with tests. (hard)
3. In `src/offload/cli.py`, wire `offload add --spec FILE` and `--confirm` into `_cmd_add` (make the positional `text` optional and error when neither text nor `--spec` is given), and update the `offload add` usage lines in `README.md`/`docs/` to match, with tests driving `cli.main` for text-only, `--spec`, and `--confirm`. (local-ok)
4. In `src/offload/engine.py`, gate `_run` before `_prepare_worktree`: a job whose `confirm` flag is true and that has no recorded approval yet calls `ask_owner(job, "confirm", ...)` so it parks in `WAITING_OWNER`, a declined or unanswered gate fails with `EXIT_GATE`, and an approval lets the job continue; add tests in `tests/test_parking.py` for the parked-then-approved, declined, and an explicit assertion that a job added without `--confirm` never reaches any `status.WAITING` state. (hard)

Test: `python3 -m pytest -q`

## Log
- step 1 done by local/harness in 384.8 s
- step 2 done by local/harness in 464.2 s
- step 3 done by local/harness in 363.8 s
- step 4 done by local/harness in 975.9 s
