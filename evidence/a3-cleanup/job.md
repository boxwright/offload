---
id: a3-cleanup
title: Sweep old job folders and rotate the ledger monthly
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: offload/a3-cleanup
---
## Goal
Finished jobs keep their clone (`work/`), their Claude session folder (`claude-home/`) and `scratch/` forever, and `ledger.jsonl` grows forever. Add a cleanup that removes the large folders of old finished jobs and moves old ledger lines into monthly archive files. The week's spend and the per-job cost table must stay correct.

Requirements:

1. `src/offload/config.py`: add one field to `Config`, in the "How jobs run" group: `keep_days: int = 14` with the comment `# finished jobs older than this lose work/, claude-home/ and scratch/; 0 turns the sweep off`. Add the same key with a one-line comment to `config.example.yaml`.

2. New module `src/offload/cleanup.py` with a module docstring and these three functions. Follow the style of `src/offload/daemon.py`: one statement per line, a docstring on each public function, lines of 120 characters at most.
   - `sweep_finished_jobs(jobs_root, keep_days, dry_run=False)` returns the list of job ids it swept (or would sweep when `dry_run` is true). A job is swept when all of these are true: its status is `done` or `failed`; its status record has no `swept` field; its `finished` field (format `offload.clock.TS_FMT`, local time) is more than `keep_days` days old. A job with no `finished` field or one that does not parse is skipped. To sweep a job, remove the directories `work`, `claude-home` and `scratch` inside the job directory if they exist (`shutil.rmtree(path, ignore_errors=True)`), then call `status.set_status(job_dir, <the same status as before>, swept=now())`. Never touch any other file in the job directory. When `keep_days` is 0 or less, return an empty list and do nothing. Use `job_dirs(jobs_root, include_hidden=False)`.
   - `rotate_ledger(ledger_path, keep_s=8 * 86400, now_ts=None)` returns the number of lines moved. A ledger line is moved when its `ts` field (epoch seconds) is older than `now_ts - keep_s` AND its calendar month (local time, from `ts`) is earlier than the current calendar month. A moved line is appended to `ledger-YYYY-MM.jsonl` (the month of the line) in the same directory as the ledger. Lines that stay are written back to the ledger through a temporary file and `os.replace`, so a crash never leaves a half-written ledger. A line that is not valid JSON, or has no numeric `ts`, stays in the ledger unchanged. If the ledger file does not exist, return 0. If no line moves, do not rewrite the ledger.
   - `run_cleanup(jobs_root, dry_run=False)` calls both with `CFG.keep_days` and `CFG.ledger`, prints one line `cleanup: swept N job(s), moved M ledger line(s)`, and returns `(swept ids, moved count)`. With `dry_run` true it does not rotate the ledger and prints `cleanup (dry run): would sweep N job(s): <ids>`.

3. `src/offload/budget.py`: `job_costs()` must also count the archive files, so an old job's cost stays in `offload status` and `offload cost`. Add `_archive_rows()` that yields the records of every `ledger-*.jsonl` file beside `LEDGER` (sorted by name, `read_jsonl(path, strict=False)`), and make `job_costs()` iterate over the archives and then the live ledger. Do NOT change `spent_since()`: the pacer reads the live ledger only.

4. `src/offload/daemon.py`: in `serve`, run the cleanup once at start (after `_requeue_interrupted`) and then at most once every 24 hours, only at a moment when no job is picked (inside the `if picked is None:` branch, before the sleep). Wrap each call in `try/except Exception` and print the error with the `[{now()}]` prefix, because a cleanup must never stop the loop.

5. `src/offload/cli.py`: new subcommand `cleanup` with the help text `remove old job folders and rotate the ledger` and one flag `--dry-run`. It takes the optional jobs root like `status` does (`jobs_root=True`). The handler imports `run_cleanup` inside the function, like the other handlers.

6. New file `tests/test_cleanup.py`. Use `tmp_path` and `make_job_dir` from `conftest`. No test may touch the real home directory. Tests:
   - a `done` job with `finished` 20 days ago loses `work/`, `claude-home/` and `scratch/`, keeps `events.jsonl` and `job.md`, and gets a `swept` field; its status is still `done`.
   - a `done` job finished 2 days ago is not swept. A `running` job with an old `finished` field is not swept. A job already carrying `swept` is not swept again.
   - `keep_days=0` sweeps nothing. `dry_run=True` returns the ids and removes nothing.
   - `rotate_ledger`: write lines with `ts` 40 days ago, 3 days ago and now, using a fixed `now_ts` in the middle of a month (for example the epoch of 2026-09-20 12:00 local time, built with `time.mktime`). The 40-day-old line moves to the right `ledger-YYYY-MM.jsonl`; the other two stay; the return value is 1; a line of invalid JSON stays in the ledger.
   - a line that is older than `keep_s` but in the current calendar month stays (use `now_ts` on the 20th and a `ts` on the 2nd of the same month).
   - after a rotation, `budget.job_costs()` still returns the archived job's total (monkeypatch `budget.LEDGER` to the tmp ledger path), and `budget.spent_since(0)` counts only the live ledger.

7. `README.md`: in the feature list, after the line that starts `- **A budget you set.**`, add: `- **It cleans up after itself.** Finished jobs older than 14 days (keep_days) lose their clone and session folders, and the ledger rotates monthly. Reports and events stay.`

## Done when
- `python3 -m pytest -q tests` passes, with at least 89 tests.
- `python3 -m offload cleanup --dry-run` prints a line that starts with `cleanup (dry run)`.
- `src/offload/cleanup.py` is under 120 lines and no line in it is longer than 120 characters.
- `spent_since` in `src/offload/budget.py` is unchanged.
