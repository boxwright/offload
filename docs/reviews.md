# Review notes

## Simplify pass, 2026-09-19 (official simplify skill, four reviewers: reuse, simplification, efficiency, altitude)

Applied, with 58 tests, ruff clean, and a live job (`jobs/demo-005`) as the guard:

- One statement per line everywhere; no semicolon chains, no lambdas bound to names, no `__import__`, no closures in the workers.
- One sandbox runner (`sandbox.run_sandbox`) and one command-line builder for both workers; one ledger reader; one job-directory lister; one reply classifier (`results.classify`) instead of text matches at call sites.
- New leaf modules (`clock`, `files`, `status`, `results`) removed every import cycle and every function-level import that existed to dodge one.
- Atomic JSON writes; every file handle closed; budget file cached by mtime; the status table reads the ledger once; CLI subcommands import only what they need.
- Deleted: the hand-rolled YAML fallback (70 lines) and its tests, the dead `state.json`, the unused `STATUSES` tuple, the fixture tests, the test facade module, history-narrating comments.
- Identity removed from code: the host name, the owner's name, the personal timezone in the limit simulation, the commit identity (now `git_user_name` / `git_user_email` in config).

Defects found by the reviewers and fixed in the same pass:

| Defect | Fix |
|---|---|
| The worker ran even when the sandbox firewall script failed (`;` joined, output discarded) | the worker starts only if the firewall came up; otherwise `SandboxError` fails the job |
| A failed `git push` still reported "done, pushed" with exit 0 | push failure is a `fail` event and exit 7 |
| A job waiting on a limit, the budget, or the owner at a daemon restart was stranded forever | every interrupted status is requeued at start (tested). Since 0.1.1 a waiting job is parked with its wake condition on disk, so a restart does not touch it |
| The subscription token was on the docker command line, visible in `ps` | passed through the process environment (`-e NAME` without a value) |
| `"529" in text` matched any text containing 529 | anchored pattern (tested) |
| A worker timeout killed only the docker client and left the container running | containers are named and killed on timeout; a timeout is an error reply, not a crash |
| A corrupt `status.json` silently became `ready` and re-ran the job | it fails the job (tested) |
| A malformed `budget.yaml` silently became defaults | it raises with the file name |
| `git clone` failure was an `assert`; `git push` could hang on a credential prompt | explicit failure; `GIT_TERMINAL_PROMPT=0` and a timeout |

## Code review pass, 2026-09-20 (official code-review skill, high effort): ten findings, ten fixed

The one that mattered: **the job's tests ran on the host.** Every worker was sandboxed, but after each step the
engine ran the test command itself, on the host, which executes code a model had just written, with access to
the token and the webhook. Tests now run in a container with no network and no secrets (`run_shell_in_sandbox`);
`run_tests_on_host: true` is the documented escape hatch. Proven live in `jobs/demo-006`: seven test runs, 0.2 s each.

Also fixed: a damaged ledger line no longer stops the pacer; group lookup survives a gid with no name; PyYAML in
the sandbox image; a job that commits nothing fails instead of reporting done; intake survives prose with a colon;
unique job ids within one second; a clear error for a missing token; budget cache keyed on mtime_ns and size; the
serve loop (now `daemon.py`) stops re-reading finished jobs. 62 tests, ruff clean.

## Deferred, written down (larger than a cleanup)

- ~~**Lazy config.**~~ Done 2026-09-22 by dogfood job `a4-lazy-config-2` (first attempt `a4-lazy-config` cancelled: its plan removed `CFG` before the users were migrated). `get_config()` / `set_config()`; tests use the `settings` fixture. `CFG` loaded at import. A `get_config()` accessor with an injectable override would make tests simpler and move the `ENGINE_GATE_WAIT_S` env read out of a dataclass default.
- **Paths for an installed package.** `budget_file` and `repos.yaml` default to the repo root, which does not exist after `pip install`. Move defaults to `~/.config/offload/` and `~/.local/state/offload/` (XDG), with `offload init` writing them. Also rename `ENGINE_CONFIG` → `OFFLOAD_CONFIG`, `~/.config/engine` → `~/.config/offload`, image and proxy names `engine-*` → `offload-*`, branch prefix `engine/` → `offload/`.
- ~~**Resumable phases.**~~ Done 2026-09-20: `progress.json` holds the phase and the step. Proof: `jobs/a2-killed/` (daemon restarted 4 s into step 2; one `plan` event; the job continued at step 2).
- ~~**Growth.**~~ Done 2026-09-21: `cleanup.py`, `keep_days`, monthly ledger archives. The dogfood branch for this item was rejected (it deleted whole job folders); see `jobs/a3-cleanup/REPORT.md`. Events are kept on purpose: they are the evidence. The month-boundary rotation has unit tests only, because every live ledger line is from the current month.
- ~~**Waits block the single-job loop.**~~ Done 2026-09-20: a wait raises `Parked`, and the loop runs the next job. Proof: `jobs/a1-gated/` and `jobs/a1-plain/`.
- ~~**`tier` in job.md is unused.**~~ Removed 2026-09-23 (the owner's decision). Every job starts on the local model; the plan, the review and a rescue are Claude's, and the models per phase are in `budget.yaml`.
- ~~**Notifier interface.**~~ Done 2026-09-23 by dogfood job `a5-notifier` ($0.54, no rescue, tests green after every step): `notifiers.py` with Discord, ntfy and none. ntfy has a fake-server test only.
- **Installer:** see the section below.
- ~~**A10 API key and pinned CLI**~~ Done 2026-09-23 by hand: `claude_auth`, `api_key_file`, `CLAUDE_CODE_VERSION` in the Dockerfile. The API-key path has a unit test only; no key exists here and a live call would be a bill.

# Installer: proven and not proven

- **Proven 2026-09-20 (maintenance window on the 5090 box, 5.5 minutes of model downtime):** `install/compose.yaml` as shipped, on the upstream llama.cpp CUDA image, with the model file, the proxy, the installer's own Docker network, speculative decoding on and off, and a tool-using task from the sandbox through the proxy to the model. Numbers are in `docs/hardware.md`. Found and fixed before the window: upstream `-fa` takes a value (`-fa on`). Script: `tools/window_test.sh`.
- **Not proven:** the 20 GB model download step of `install.sh` end to end (the file was already on disk; the URL and licence were verified), a machine with no Docker or no NVIDIA runtime, and any 24 GB card. Context sizes and memory figures for the 4-bit build are estimates.

## The sandbox was rewritten before release (2026-09-20)

The first sandbox was a modified copy of Anthropic's reference devcontainer. That repository is "all rights
reserved", so those files could not ship under Apache-2.0. The replacement is original and tighter: root raises
the firewall and then drops every capability before the worker runs (the reference lets the worker re-run the
firewall script through sudo); the paid worker may reach `api.anthropic.com` only, the local worker nothing beyond
its Docker network; no GitHub, npm or PyPI; no GitHub API lookup per container; the image went from 2.4 GB to 733 MB.
Proven from inside the container and with a full job.
- ~~**A7 owner answers from Discord**~~ Built 2026-09-24 by dogfood job `a7-discord-inbox` ($0.82, no rescue, 180 tests) as a REST poll with a bot token (`docs/design/owner-answers-from-chat.md`, option C). Unit tests against a fake server; the live proof waits for the owner's bot token and ids.
