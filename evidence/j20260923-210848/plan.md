# Plan — j20260923-210848

1. In `src/offload/jobs.py` add a `Job.note` attribute reading an optional `<job>/note.txt`, and in `src/offload/prompts.py` make `step_brief` append that note to the brief when present, with a test in `tests/test_job.py` covering both the empty and the present case. (local-ok)
2. Add `retry(job_dir, note=None, replan=False)` to `src/offload/jobs.py`: refuse (return non-zero) with a message naming the job's current state unless `status.job_status` says `failed`; otherwise write `note.txt` when a note is given, delete `progress.json`, `cancel`, `answer.txt` and the terminal report leftovers, delete `plan.txt`/`plan.md` only when `replan` is set so the stored plan (and always the stored `job.md` spec and `intake.json`) is reused, then `status.set_status(..., READY)` so the daemon re-runs it with no intake call. (hard)
3. Wire the command into `src/offload/cli.py`: a `_cmd_retry` handler plus a `retry` subparser taking `job_dir`, `--note TEXT` and `--replan`, returning the exit code from `jobs.retry` so a non-failed job exits non-zero. (local-ok)
4. Add `tests/test_retry.py` covering the three behaviours end to end through `cli.main`: `--note` lands in the step brief handed to the worker, `--replan` drops the stored plan while keeping `job.md`/`intake.json` so intake is skipped, and retrying a `running`/`done` job exits non-zero with its state named in the output. (hard)
5. Document the command in `README.md` (the `## Use` command list) and in `public/CHANGELOG.md`. (local-ok)

Test: python3 -m pytest -q

## Log
- step 1 done by local/harness in 288.2 s
- step 2 done by local/harness in 427.0 s
- step 3 done by local/harness in 139.4 s
- step 4 done by local/harness in 735.1 s
- step 5 done by local/harness in 86.1 s
