# Plan — m5-package

1. Create `pyproject.toml` (boxwright-offload 0.1.0, src layout, pyyaml, dev extras, `offload = offload.cli:main`) plus `src/offload/__init__.py` and `__main__.py`, and move `engined/config.py` to `src/offload/config.py` unchanged. (local-ok)
2. Split `engined/engined.py` into `limits.py`, `budget.py` (LEDGER/BUDGET_FILE globals read at call time, `spent_since`, `pace_status`, `budget_wait`, `model_for`, `job_cost`, `cost_table`), `notify.py` (`notify`, `ask_jon`→`ask_owner`, same event/file names), `workers.py` (Hermes path, `qwen`, `local_worker`, and the `hermes`/`local_worker` config keys deleted; callers call `local_harness` directly), `jobs.py`, and `engine.py`, breaking the jobs↔notify cycle with function-local imports and keeping config loaded once in `offload.config`. (hard)
3. Write `src/offload/cli.py` with argparse subcommands serve/run/add/status/cost/report/answer/digest/budget/pause/unpause each with one-line help and a `main()` returning an exit code, reduce `engined/engined.py` to a ≤10-line `sys.path` shim, and delete `engined/config.py`. (local-ok)
4. Update `tests/conftest.py` to put `src` on `sys.path` and expose the `engined`/`engined_isolated` fixtures as a delegating facade over the package modules while monkeypatching `offload.budget.LEDGER`/`BUDGET_FILE`, and repoint `tests/test_config.py` at `src/offload/config.py`, retargeting only the two now-removed `c.hermes` assertions to a surviving path key while keeping every other assertion. (hard)
5. Strip the `hermes` and `local_worker` keys from `config.example.yaml` and check each done-when: 45+ tests pass, `--help` lists eleven subcommands, `budget` prints JSON through both the package and the shim, `grep -rn hermes src/ engined/ config.example.yaml` is empty, and no `src/offload/` file exceeds 250 lines. (local-ok)

Test: python3 -m pytest -q tests

## Log
- step 1 done by local/harness in 739.7 s
- step 2 done by local/harness in 1036.5 s
- step 3 done by local/harness in 824.7 s
- step 4 done by local/harness in 727.8 s
- step 5 done by local/harness in 599.3 s
