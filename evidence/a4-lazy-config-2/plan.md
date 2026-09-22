# Plan — a4-lazy-config-2

Repo read: 89 tests pass today; `CFG` is used in 10 src modules plus `tests/test_setup_cmds.py` (which monkeypatches `setup_cmds.CFG`), and `budget.py`'s docstring names `LEDGER`/`BUDGET_FILE`.

1. In `src/offload/config.py` add `_config = None`, `get_config()` (loads on first call, caches) and `set_config(config)` (installs a Config or `None`, returns the previous value) with the required docstrings and two new module-docstring lines, leaving `CFG = load_config()` in place so every current importer keeps working. (local-ok)
2. Switch `cleanup`, `cli`, `daemon`, `engine`, `jobs`, `notify`, `sandbox`, `setup_cmds`, `workers` to `from offload.config import get_config` and `get_config().<name>` (one `config = get_config()` at the top of any function using three or more values, `settings` as the local name in `setup_cmds` so the `config` module import for `config.data_dir()` still works, never at module level or in a default argument), and in the same step change the `temp_install` fixture in `tests/test_setup_cmds.py` from `monkeypatch.setattr(setup_cmds, "CFG", ...)` to installing a freshly loaded config via `config.set_config` and restoring it. (hard)
3. Add the `settings` fixture to `tests/conftest.py`, make `api_isolated` depend on it instead of patching, point `quiet` in `tests/test_parking.py` and the last test in `tests/test_cleanup.py` at `settings`/`settings.ledger`, and in the same step delete `LEDGER`/`BUDGET_FILE` from `src/offload/budget.py` so every use reads `get_config().ledger` / `get_config().budget_file` at call time, keeping the budget file path part of the `_budget_cache` key and rewriting the docstring line that named the two constants. (hard)
4. Delete `CFG = load_config()` from `src/offload/config.py` (now unused) and add the three accessor tests to `tests/test_config.py`: identity across two `get_config()` calls, `set_config(x)` returning the previous value, and a reload after `set_config(None)` with `OFFLOAD_CONFIG` pointed at a tmp file setting `max_test_fails: 7`, restoring the previous config at the end. (hard)
5. Add the laziness test to `tests/test_config.py`: a subprocess `python3 -c "import offload.daemon, offload.cli, offload.engine"` with `OFFLOAD_CONFIG` pointing at a tmp file containing `nonsense_key: 1` and `PYTHONPATH` set to the repo's `src`, asserting exit code 0. (local-ok)

Test: `python3 -m pytest -q tests`

## Log
- step 1 done by local/harness in 55.8 s
- step 2 done by local/harness in 791.2 s
- step 3 done by local/harness in 743.0 s
- step 4 done by local/harness in 100.0 s
- step 5 done by local/harness in 151.0 s
