---
id: m5-config
title: Move every machine-specific constant into a config file with safe defaults
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: engine/m5-config
tier: qwen
---
## Goal
`engined/engined.py` hardcodes values that belong to one machine: `HERMES`, `VENV_BIN`, `TOKEN_FILE`, `SANDBOX_IMAGE`, `LLAMA_HOST`, the Docker network name `llama_default`, `WEBHOOK_FILE`, `LEDGER`, the pause file path, `CLAUDE_TOOLS`, `STEP_TIMEOUT`, `MAX_TEST_FAILS`, `GATE_WAIT_S`. Strangers will install this on their own machines. Introduce a small config layer so that every one of these comes from a YAML file, with defaults equal to today's values so behaviour does not change when no file exists.

Requirements:
- New module `engined/config.py` with a dataclass `Config` and `load_config(path=None) -> Config`. Lookup order: explicit path argument, then the `ENGINE_CONFIG` environment variable, then `~/.config/engine/config.yaml`, then defaults. `~` and environment variables in string values are expanded. Unknown keys raise a `ValueError` that names the key. PyYAML is optional at import time: if it is missing and a config file exists, raise a clear error; if no file exists, defaults work without PyYAML.
- `engined/engined.py` reads these values from one module-level `CFG = load_config()` object (for example `CFG.sandbox_image`, `CFG.docker_network`, `CFG.local_model_host`). Remove the old constants. Keep function signatures and event names unchanged.
- The existing tests patch `LEDGER` and `BUDGET_FILE` on the module. Keep those two names working (module attributes that the code reads at call time), or update the fixtures in `tests/conftest.py` so every existing test still passes.
- Add `config.example.yaml` at the repo root: every key, its default, one comment line each.
- Add `tests/test_config.py`: defaults without a file, file overrides, `ENGINE_CONFIG` lookup, `~` expansion, unknown key error.

## Done when
- `python3 -m pytest -q tests` passes with at least 40 tests.
- `grep -n "172.18.0.2\|llama_default\|engine-sandbox:latest\|discord-webhook" engined/engined.py` prints nothing: those strings live only in `engined/config.py` defaults and `config.example.yaml`.
- With no config file present, `python3 engined/engined.py budget` still prints the pacer JSON.
