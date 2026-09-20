---
id: m5-package
title: Turn the single-file daemon into an installable Python package named offload
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: engine/m5-package
tier: qwen
allow_test_edits: true
---
## Goal
`engined/engined.py` is one 600-line script. Strangers will read this code. Restructure it into a small, readable package without changing behaviour. The product is named **Offload**; the package and the command are `offload`.

Target layout (src layout):
- `pyproject.toml`: project name `boxwright-offload`, version `0.1.0`, Python >= 3.10, dependency `pyyaml`, optional dev dependencies `pytest`, `ruff`; console script `offload = offload.cli:main`; setuptools with `src/` layout.
- `src/offload/__init__.py` (version string only), `src/offload/__main__.py` (calls `cli.main`).
- `src/offload/config.py`: move `engined/config.py` here unchanged in behaviour.
- `src/offload/limits.py`: `LIMIT_RE`, `parse_reset`.
- `src/offload/budget.py`: budget file loading, `week_start`, ledger functions, `pace_status`, `budget_wait`, `model_for`, `job_cost`, cost table.
- `src/offload/notify.py`: `notify`, `ask_jon` (rename to `ask_owner`; keep the event names and file names unchanged).
- `src/offload/workers.py`: `sh`, `_docker`, the sandbox preamble, the Claude worker (`claude`) and the local worker (`local_harness`). **Delete the legacy Hermes path** (`qwen`, the `hermes` and `local_worker` config keys, and `local_worker()` itself): the local worker is always the harness.
- `src/offload/jobs.py`: `Job`, status helpers, `add`, `known_repos`, `intake`, `write_report`, status table.
- `src/offload/engine.py`: prompts, `rules_for`, `is_stuck`, `run_tests`, `run`, `serve`, `digest`.
- `src/offload/cli.py`: an `argparse` CLI with subcommands `serve`, `run`, `add`, `status`, `cost`, `report`, `answer`, `digest`, `budget`, `pause`, `unpause`, each with a one-line help string. `main()` returns an exit code.
- `engined/engined.py` becomes a shim of at most 10 lines that adds `src/` to `sys.path` and calls `offload.cli.main()`, so the running service keeps working. Delete `engined/config.py`.
- No module-level side effects except loading the config once in one place (`offload.config.CFG` or a `get_config()` accessor). No circular imports.
- Update `tests/` to import from the package (put `src` on the path in `tests/conftest.py`). Keep every existing assertion. Tests that patched module attributes such as `LEDGER` must patch the new home of that value.
- Update `config.example.yaml`: remove the deleted keys.

## Done when
- `python3 -m pytest -q tests` passes with at least 45 tests.
- `PYTHONPATH=src python3 -m offload --help` lists all eleven subcommands, and `PYTHONPATH=src python3 -m offload budget` prints the pacer JSON.
- `python3 engined/engined.py budget` still works through the shim.
- `grep -rn "hermes" src/ engined/ config.example.yaml` prints nothing.
- No file in `src/offload/` is longer than 250 lines.
