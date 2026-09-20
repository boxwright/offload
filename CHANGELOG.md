# Changelog

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
