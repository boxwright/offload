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
