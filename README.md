# Offload

**Use less credits with your home box AI.**

Offload is a small daemon for people who own a GPU box and pay for Claude. You give it one line about a change you want in a repo. A model on your own GPU does the typing. Claude only plans, reviews, and rescues. You get a pushed branch, a report, and a message when it needs a decision.

On our own jobs, Claude's share of the work was **36 seconds out of 13 minutes**.

> Status: 0.1.0, the first public release. Measured on one machine so far. Hardware reports are the most useful thing you can send.

## Is this for you?

Read this before anything else. Offload needs:

- a Linux box with an **NVIDIA GPU with 24 GB of VRAM or more** (we measured on 32 GB)
- 32 GB of RAM, 60 GB of free disk, Docker with the NVIDIA Container Toolkit
- your own **Claude Pro or Max** subscription

A 32 GB laptop is **not** a practical host. We measured it and wrote down why: [docs/hardware.md](docs/hardware.md).
Check your machine without installing anything:

```bash
curl -fsSL https://raw.githubusercontent.com/boxwright/offload/main/install/preflight.sh | bash
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/boxwright/offload/main/install/install.sh | bash
```

It asks before every download, tells you sizes first, and never sees your Claude login: you create your own token with `claude setup-token`.

## Use

```bash
offload demo             # a two-minute job on a sample repo, to watch it work
offload add "In my-repo, add input validation to the signup form and tests for it"
offload status          # every job: state, cost so far, last event
offload report <job>    # what changed, what it cost, what was decided and by whom
offload cost            # this week against your allowance
offload answer <job> yes
```

## How it works

```
 you ── one line ──▶ intake (Claude, once) ──▶ plan (Claude, once)
                                                  │
                         ┌────────────────────────▼────────────────────────┐
                         │  steps: local model on your GPU, in a sandbox   │◀─ test output fed back
                         │  stuck or no progress? ──▶ one Claude rescue    │
                         └────────────────────────┬────────────────────────┘
                                                  ▼
                        review (Claude, once) ──▶ commit, push, report, notify
```

- **One harness, two brains.** Both workers are Claude Code in print mode. The local one talks to a small proxy in front of your model server, so there is no second agent to install.
- **Sandboxed by default.** Every worker runs unprivileged in a container with a default-deny firewall. The local worker's container never holds your Claude token and has no internet.
- **Three questions, ever.** It asks you before spending money, publishing, or deleting. Everything else it decides and writes down.
- **Rate limits are its problem, not yours.** On a limit it reads the reset time, parks the job, and resumes the same session later.
- **A waiting job does not block the queue.** A job that waits for you, a limit, or the budget is parked, and the next job runs. After a restart a job continues from the step it was on. It does not plan again.
- **A budget you set.** It paces Claude use across the week and keeps a share for your own sessions.

## What it saves

Measured on real jobs, with the evidence in this repo ([evidence/](evidence/), [calibration/](calibration/RESULTS.md)):

| Job | Local model | Claude |
|---|---|---|
| Fix a bug in a small repo (`offload demo`) | 58 s, 3 sessions | 20 s, 2 calls |
| Write a 33-test suite, 446 lines, 5 files | 740 s, 7 sessions | 36 s, 2 calls |
| Move 13 hardcoded settings into a config layer, with tests | 868 s, 5 sessions | 68 s, 2 calls |

Those last two jobs were Offload working on its own source code.

## What it cannot do

- Make a small GPU run a big model.
- Guarantee the local model gets vague or sprawling tasks right. It escalates when it stalls, and the report says when it did.
- Run on Windows, or with a Mac as the host.

## Safety model, in short

Every model runs in a container, unprivileged, behind an outbound firewall it cannot change, and the worker does not start if the firewall does not. The paid worker can reach `api.anthropic.com` and nothing else. The local model's container never holds your Claude login and cannot reach the internet at all. Your project's tests run with no network at all, because tests are code the model just wrote. Workers get an allowlist of tools with no push, sudo, ssh, docker, curl or pip on it. Money, publishing and deletion stop and ask you. The full model, including what it does not protect against: [docs/safety.md](docs/safety.md). Questions people ask, including the one about Claude's terms: [docs/faq.md](docs/faq.md).

## License

Apache-2.0. The model it downloads, Qwen3.8-27B (Unsloth GGUF build), is also Apache-2.0.
"Claude" and "Claude Code" are Anthropic's. Offload is an independent tool that works with Claude Code; you bring your own subscription and it is never shared.
