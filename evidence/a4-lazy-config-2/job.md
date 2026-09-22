---
id: a4-lazy-config-2
title: Load the config on first use through get_config(), with an override for tests
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: offload/a4-lazy-config-2
allow_test_edits: true
---
## Goal
`src/offload/config.py` ends with `CFG = load_config()`, so the config file is read when any module is imported. `src/offload/budget.py` copies two values at import (`LEDGER = CFG.ledger`, `BUDGET_FILE = CFG.budget_file`), and the tests redirect them with `monkeypatch.setattr(budget, "LEDGER", ...)`. Replace this with an accessor that loads the config on first use and that a test can override. Behaviour for a user must not change.

Requirements:

1. `src/offload/config.py`: delete the line `CFG = load_config()`. Add below `load_config`:
   - a private module variable `_config = None`
   - `get_config()`: returns the current `Config`. On the first call it runs `load_config()` and keeps the result. Docstring: one sentence.
   - `set_config(config)`: makes `config` the current Config and returns the previous value (a `Config` or `None`). Passing `None` means "load again on the next `get_config()`". Docstring: say it is for tests and for a long-running process that wants to re-read the file.
   Update the module docstring: add two lines that describe `get_config()` and `set_config()`.

2. In every module under `src/offload/` replace each use of `CFG.<name>` with `get_config().<name>`, and change the import `from offload.config import CFG` to `from offload.config import get_config`. When a function uses three or more config values, read it once at the top of the function: `config = get_config()` and then `config.<name>`. Never call `get_config()` at module level or in a default argument value. The modules are: budget, cleanup, cli, daemon, engine, jobs, notify, sandbox, setup_cmds, workers. `setup_cmds.py` imports the `config` module for `config.data_dir()`: keep that working and name the local variable `settings` in that module to avoid shadowing the module name.

3. `src/offload/budget.py`: delete the module constants `LEDGER` and `BUDGET_FILE`. Every place that used them reads `get_config().ledger` or `get_config().budget_file` at call time. The budget cache (`_budget_cache`) must stay keyed so that a different budget file path is never answered from the cache of another path: include the path in the cache key if it is not already there.

4. `tests/conftest.py`: add a fixture named `settings`:
   ```python
   @pytest.fixture
   def settings(tmp_path):
       """A Config whose files all live in tmp_path, installed for the length of the test."""
       test_config = dataclasses.replace(
           config.Config(), jobs_root=str(tmp_path / "jobs"), ledger=str(tmp_path / "ledger.jsonl"),
           budget_file=str(tmp_path / "budget.yaml"), repos_file=str(tmp_path / "repos.yaml"),
           token_file=str(tmp_path / "claude-token"), webhook_file=str(tmp_path / "discord-webhook"),
           pause_file=str(tmp_path / "PAUSE"))
       previous = config.set_config(test_config)
       yield test_config
       config.set_config(previous)
   ```
   Change the `api_isolated` fixture to depend on `settings` instead of patching `budget.LEDGER` and `budget.BUDGET_FILE`. In `tests/test_parking.py` the autouse fixture `quiet` must depend on `settings` and stop patching `budget.LEDGER` / `budget.BUDGET_FILE`. In `tests/test_cleanup.py` the last test must use `settings` and write its ledger to `settings.ledger`. In `tests/test_parking.py`, the two tests that patch `workers._blocked_until_file` may keep that patch.
   After the change, `grep -rn "LEDGER\|BUDGET_FILE\|\bCFG\b" src tests` prints nothing.

5. `tests/test_config.py`: keep every existing test passing. Add three tests: `get_config()` returns the same object on two calls; `set_config(x)` makes `get_config()` return `x` and returns the previous value; after `set_config(None)`, `get_config()` loads again (point `OFFLOAD_CONFIG` at a tmp file that sets `max_test_fails: 7` with `monkeypatch.setenv`, call `set_config(None)`, check the value is 7, and restore the previous config at the end of the test).

6. Add one test to `tests/test_config.py` that proves the import is lazy: run `python3 -c "import offload.daemon, offload.cli, offload.engine"` in a subprocess with the environment variable `OFFLOAD_CONFIG` pointing at a file that contains an unknown key (`nonsense_key: 1`) and `PYTHONPATH` set to the repo's `src` directory. The exit code must be 0, because nothing reads the config at import.

## Done when
- `python3 -m pytest -q tests` passes with at least 91 tests.
- `grep -rn "LEDGER\|BUDGET_FILE\|\bCFG\b" src tests` prints nothing.
- `grep -n "^CFG\|^_config = load_config\|= get_config()$" src/offload/*.py | grep -v "    "` prints nothing (no module-level load).
- `python3 -m offload budget` still prints the pacer JSON.
- Do not change any behaviour, event name, CLI command, or config key. Do not edit files outside `src/offload/` and `tests/`.
