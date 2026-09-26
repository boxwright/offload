# Plan — j20260924-082225

1. In `src/offload/jobs.py`, parse the optional front-matter `checks` key into `Job.checks` (default `[]`, accepting both an inline bracketed list and indented `- ` block lines, which `_parse_front_matter` currently drops), raise a job error whose message names `checks` when the value is not a list of strings, guard `daemon._run_and_report`/`_intake` so an unparsable job.md fails the job instead of the loop, and add tests in `tests/test_job.py` for present/absent/malformed values. (hard)
2. In `src/offload/workers.py`, factor the host-or-sandbox command run out of `run_tests` into a reusable helper that runs one shell command in the job worktree with the same working directory, environment, no network and the existing container resource limits, returning exit code and combined output, leaving `run_tests` behaviour and its `tests` event unchanged. (local-ok)
3. In `src/offload/engine.py`, run each check once through that helper after the push and before the `done` event, record one `check` event per command with its command, exit code and the first 500 characters of combined output, and on any non-zero exit emit `fail` with reason `checks` and return a new checks exit code (no Claude call, no retry), with tests covering all-pass → done and one-fail → failed with the branch still pushed. (hard)
4. In `src/offload/report.py`, render a `## Checks` section from the `check` events listing each command as `pass` or `fail` with the captured output for failures, omitted entirely when the job has no check events, plus tests rendering both outcomes and the no-checks case. (local-ok)
5. Document the optional `checks:` key with an example in `jobs/_templates/job.md` and in the intake prompt's spec keys in `src/offload/prompts.py` so drafted specs may emit it. (local-ok)

Test: `python3 -m pytest -q tests`

## Log
- step 1 done by local/harness in 1018.9 s
- step 2 done by local/harness in 380.3 s
- step 3 done by local/harness in 192.4 s
- step 1 done by local/harness in 382.2 s
- step 2 done by local/harness in 136.6 s
- step 3 done by local/harness in 562.1 s
- step 4 done by local/harness in 347.9 s
- step 5 done by local/harness in 391.2 s
