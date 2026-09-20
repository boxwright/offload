# Plan — m5-tests

1. Add `tests/conftest.py` with a fixture that loads `engined/engined.py` via `importlib.util.spec_from_file_location("engined", ...)` from the repo root and a fixture that monkeypatches the module's `LEDGER` and `BUDGET_FILE` globals plus a helper to build a job dir with `job.md` under `tmp_path`. (local-ok)
2. In `engined/engined.py`, extract the inline STUCK regex at line 315 into a module-level `is_stuck(text) -> bool` with the same pattern `r"^\s*STUCK\b(?!\s*:\s*no\b)"` and `re.M`, and call it from `run` — no other behaviour change. (local-ok)
3. Write `tests/test_time.py` covering `parse_reset` (explicit tz-aware `now`: same-day 7pm with `(America/New_York)`, a past time rolling to tomorrow, `3:30am`, `in 45 minutes`, no-reset → None) and `week_start` (Thursday `now` with `week_resets: "Tue 22:00"` → previous Tuesday 22:00; Tuesday 21:00 `now` → Tuesday a week earlier). (hard)
4. Write `tests/test_budget.py` covering `ledger_add`/`spent_since`/`job_cost` round trip against a `tmp_path` ledger and `pace_status` for empty ledger (allowed), spend far above even pace (not allowed, positive wait), and spend at/above allowance (not allowed). (hard)
5. Write `tests/test_job.py` covering `Job` front-matter parsing (id/repo/branch/test keys, default `python3 -m pytest -q`, inbox job with no `repo`), `job_status` defaulting to `ready` when `job.md` exists, `set_status` persisting fields to `status.json`, and `is_stuck` for `STUCK — reason`, `STUCK: no — done`, and the word mid-sentence. (local-ok)
6. Run the suite from the repo root, confirm at least 18 tests pass and that no test writes outside `tmp_path` or touches network/Docker. (local-ok)

Test: `python3 -m pytest -q tests`

## Log
- step 1 done by qwen/hermes in 81.9 s
- step 2 done by qwen/hermes in 159.2 s
- step 3 done by qwen/hermes in 101.9 s
- step 4 done by qwen/hermes in 171.7 s
- step 5 done by qwen/hermes in 90.6 s
- step 6 done by qwen/hermes in 28.0 s
