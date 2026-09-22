# Plan — a3-cleanup

Repo read. `budget.py`, `daemon.py`, `cli.py`, `config.py`, `conftest.py` and the existing 81-test suite give a clear shape for the work.

1. In `src/offload/config.py` add `keep_days: int = 14` with its comment to the "How jobs run" group of `Config`, add the matching commented key to `config.example.yaml`, and insert the `- **It cleans up after itself.** ...` bullet after the `- **A budget you set.**` line in `README.md`. (local-ok)
2. Write `src/offload/cleanup.py` (under 120 lines, 120-char lines, docstring per public function, daemon.py style) with `sweep_finished_jobs`, `rotate_ledger` (month-aware, temp file + `os.replace`, bad lines kept) and `run_cleanup`. (hard)
3. In `src/offload/budget.py` add `_archive_rows()` yielding records of every `ledger-*.jsonl` beside `LEDGER` sorted by name, and make `job_costs()` iterate archives then the live ledger, leaving `spent_since` untouched. (local-ok)
4. In `src/offload/daemon.py` `serve`, call the cleanup after `_requeue_interrupted` and at most every 24 h inside the `if picked is None:` branch before the sleep, each call wrapped in `try/except Exception` printing with the `[{now()}]` prefix. (local-ok)
5. In `src/offload/cli.py` add the `cleanup` subcommand (help `remove old job folders and rotate the ledger`, `--dry-run`, `jobs_root=True`) with a handler that imports `run_cleanup` inside the function. (local-ok)
6. Write `tests/test_cleanup.py` using `tmp_path` and `make_job_dir`, covering the sweep cases (old done job, recent job, running job, already-swept, `keep_days=0`, `dry_run`), `rotate_ledger` with a fixed `now_ts` at 2026-09-20 12:00 local via `time.mktime` (40/3/0-day lines, invalid JSON, same-month line stays), and `job_costs()`/`spent_since(0)` after rotation with `budget.LEDGER` monkeypatched. (hard)

Test: python3 -m pytest -q tests

## Log
- step 1 done by local/harness in 100.5 s
- step 2 done by local/harness in 967.7 s
- step 3 done by local/harness in 233.3 s
- step 4 done by local/harness in 168.2 s
- step 5 done by local/harness in 62.5 s
- step 6 done by local/harness in 367.2 s
