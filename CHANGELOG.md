# Changelog

## 0.1.1 — not released

- A job that waits for the owner, a provider limit, or the budget is parked, and the daemon runs the next
  job. Before, one open gate held the queue for up to a day.
- A job continues from its checkpoint (`progress.json`: phase and step). A restart or a park no longer sends
  the job back to the planner. A rate limit blocks Claude calls for every job until the reset time, and the
  interrupted call resumes its session.
- At start the daemon kills worker containers that a stopped daemon left running. Worker containers carry
  the label `offload.role=worker`.
- `offload run` exits with code 10 when the job parks.
- A second model measured on the default install: Qwen3-Coder-30B-A3B-Instruct (UD-Q4_K_XL, 17.7 GB). 299 tok/s,
  20.8 GB of VRAM at 65k context, calibration 5/5, one real job. Numbers and the 24 GB estimate in `docs/hardware.md`.
- `offload add --spec FILE [--confirm]`: a job.md-style spec goes straight to `ready`, skipping intake. `--confirm`
  parks the job until the owner answers yes. A one-line job now posts its drafted spec to the owner.
- The planner has `plan_max_turns` (default 20; the old fixed 8 ran out on a 2,500-line repository) and a recovery
  ladder: a plan with no steps is asked again with ten more turns, then with a narrowed prompt, up to
  `max_plan_attempts` (budget.yaml, default 2). `plan_reads: index` hands the planner a file tree instead of the
  files, with `Read` and `cat` removed from its tools; `full` is the default and is unchanged.
- `offload repo add <path-or-url> "<description>"` verifies the repository with `git ls-remote` and writes a quoted
  line to `repos.yaml`; `offload repo list`. A `repos.yaml` that does not parse names its line, and intake asks the
  owner which repository instead of failing the job.
- A skill for Claude Code sessions, `skills/offload/SKILL.md` (install: `cp -r skills/offload ~/.claude/skills/`),
  and `docs/use.md`: how to register a repository, write a spec, submit, watch, answer, and review the branch.
- `bin/offload-remote` reads the box's name from `~/.config/offload/host` when `OFFLOAD_HOST` is unset.
- `offload report` on an unfinished job prints one line instead of a traceback.
- Fixed: a job re-queued by `offload retry` was invisible to a running daemon until a restart.
- The unused `tier` key is gone from job files and from intake. A job file that still has it is accepted and the key is ignored.
- `claude_auth: api_key` with `api_key_file`: the paid worker can run on an Anthropic API key instead of a
  subscription token. The sandbox image pins the Claude Code version (`CLAUDE_CODE_VERSION` build argument,
  2.1.278), so a CLI update cannot change how the worker signs in until the pin is raised.
- Notifiers: `notifier: discord` (the default, unchanged), `ntfy` (`ntfy_url`, optional `ntfy_token_file`), or `none`.
  Both are tested against a fake HTTP server. ntfy is not yet proven against a real server.
- Every worker container is capped: 4 GB of memory with no swap, 2 CPUs, 512 processes, and `no-new-privileges`
  (`sandbox_memory`, `sandbox_cpus`, `sandbox_pids`). The proxy in `install/compose.yaml` already had caps; a proxy
  started by hand with `docker run` should get the same flags.
- The config loads on first use (`get_config()`), not at import. `set_config()` lets a test or a long-running
  process replace or re-read it.
- Cleanup: a finished job older than `keep_days` (default 14, 0 turns it off) loses `work/`, `claude-home/` and
  `scratch/`. Its report, events and status stay. Ledger lines that are older than eight days and from an earlier
  month move to `ledger-YYYY-MM.jsonl`. The pacer reads the live ledger; the cost table reads the archives too.
  The daemon does this once a day while idle. `offload cleanup [--dry-run]` does it on demand.
- `offload cancel <job>`: a queued or parked job fails at once. A running job stops before its next worker call,
  and its current worker container is killed.
- `offload retry <job> [--note TEXT] [--replan]`: re-queues a failed job, reusing its stored spec (`job.md`,
  `intake.json`) so the daemon re-runs it without another intake call. A `--note` is appended to the next run's
  step brief. `--replan` drops the stored plan so it is made again; without it the plan is reused. A job that is
  not `failed` is refused, and its current state is named.
- The planner is told to order steps so that the tests pass after each one. A plan that removed a name in step 1
  and updated its users in step 3 could not pass the tests in between.
- The systemd unit stops in 15 seconds (`TimeoutStopSec=15`). A worker container ignores SIGTERM, so a stop waited
  for the 90-second default. An existing install keeps its unit file: add the line by hand, or delete the unit and run `offload init`.
- Fixed: a review that contained both verdict words ("APPROVE — no." and then "REQUEST_CHANGES") counted as an
  approval, and the branch was pushed. A reply with both words is now a request for changes.

## 0.1.0 — 2026-09-20

First public release.

- The daemon (`offload serve`): intake, plan, steps, tests after every step, one rescue for a stalled step,
  review, one commit, push, report, notification.
- Two workers on one harness: Claude Code in print mode, against Anthropic or against a local
  OpenAI-compatible model server through a translation proxy.
- Sandbox: a container per worker call with an outbound firewall; the project's tests run with no network.
- Rate-limit handling (wait, then resume the same session), a weekly budget pacer, three owner gates.
- Commands: init, doctor, demo, serve, run, add, status, cost, report, answer, digest, budget, pause, unpause.
- Installer with a read-only preflight and an optional speculative-decoding setting with a recommendation.
- Measured on one machine (RTX 5090, Qwen3.8-27B). See `docs/hardware.md` for what is and is not tested.
