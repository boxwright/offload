# Plan — m5-config

1. Write `engined/config.py`: a frozen-ish `Config` dataclass holding defaults equal to today's constants (hermes, venv_bin, token_file, sandbox_image, local_model_host, docker_network `llama_default`, webhook_file, ledger, pause_file, budget_file, claude_tools, step_timeout, max_test_fails, gate_wait_s) plus `load_config(path=None)` with lookup order explicit path → `ENGINE_CONFIG` → `~/.config/engine/config.yaml` → defaults, `os.path.expanduser`+`expandvars` on every string value, a `ValueError` naming any unknown key, and a deferred `import yaml` that raises a clear error only when a config file actually exists. (hard)
2. Rewrite the constant block in `engined/engined.py` to `CFG = load_config()` (imported by path since engined.py is loaded as a standalone module by the tests, not a package) and replace every use site — lines 76, 88, 110, 121, 141/149/381/502, 189–197, 202, 238, 250–252, 312, 438, 468, 551 — with `CFG.*`, keeping `LEDGER = CFG.ledger` and `BUDGET_FILE = CFG.budget_file` as module-level names still read at call time so `tests/conftest.py` monkeypatching keeps working, and keeping the literal strings `172.18.0.2`, `llama_default`, `engine-sandbox:latest`, `discord-webhook` out of the file entirely. (hard)
3. Add `config.example.yaml` at the repo root listing every key with its default value and one comment line each. (local-ok)
4. Add `tests/test_config.py` covering defaults with no file, per-key file overrides, `ENGINE_CONFIG` lookup, explicit-path precedence over the env var, `~` and `$VAR` expansion, and the unknown-key `ValueError` message naming the key — note PyYAML is **not installed** in this environment, so file-based tests must not be skipped away (either write a tiny dependency-free key/value YAML reader inside `config.py` used when PyYAML is absent, or install PyYAML); at least 7 new tests are needed to reach the 40-test floor. (hard)
5. Run `python3 -m pytest -q tests`, then verify `grep -n "172.18.0.2\|llama_default\|engine-sandbox:latest\|discord-webhook" engined/engined.py` prints nothing and `python3 engined/engined.py budget` still prints the pacer JSON with no config file present. (local-ok)

Test: python3 -m pytest -q tests

## Log
- step 1 done by qwen/hermes in 394.3 s
- step 2 done by qwen/hermes in 107.6 s
- step 3 done by qwen/hermes in 147.7 s
- step 4 done by qwen/hermes in 201.8 s
- step 5 done by qwen/hermes in 16.5 s
