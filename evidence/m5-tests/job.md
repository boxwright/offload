---
id: m5-tests
title: Add a pytest suite for the engine's pure logic
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: engine/m5-tests
tier: qwen
---
## Goal
`engined/engined.py` has no tests. Add a `tests/` directory with pytest tests for the pure logic, so later refactors are safe. Load the module with `importlib.util.spec_from_file_location("engined", "engined/engined.py")` from the repo root (it is a script, not a package). Tests must not use the network, Docker, a model, or the real home directory: use `tmp_path` and `monkeypatch` to point `LEDGER`, `BUDGET_FILE` and job directories at temporary paths.

Cover at least:
- `parse_reset`: "resets 7pm (America/New_York)" later the same day, a time already past today rolls to tomorrow, "resets 3:30am", "resets in 45 minutes", and text with no reset returns None. Pass an explicit `now`.
- `week_start`: for a `now` on a Thursday with `week_resets: "Tue 22:00"` it returns the previous Tuesday 22:00; for a `now` on Tuesday 21:00 it returns the Tuesday a week earlier.
- `pace_status`: an empty ledger allows; a ledger entry far above even pace does not allow and returns a positive wait; spend at or above the allowance does not allow.
- `ledger_add` + `spent_since` + `job_cost` round trip.
- `job_status` / `set_status`: default is "ready" when `job.md` exists, and `set_status` persists fields.
- The STUCK detection regex used in `run`: a final answer starting with `STUCK — reason` matches, `STUCK: no — done` does not, and the word inside a sentence does not. If the regex is inline, extract it into a small module-level function `is_stuck(text) -> bool`, use it in `run`, and test that function.
- `Job` parsing: front matter keys, default test command, an inbox job without `repo`.

## Done when
- `python3 -m pytest -q tests` passes with at least 18 tests.
- No test touches the network, Docker, or paths outside `tmp_path`.
- The only change to `engined/engined.py` is the `is_stuck` extraction, with behaviour unchanged.
