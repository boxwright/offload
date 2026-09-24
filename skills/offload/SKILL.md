---
name: offload
description: Use when the user wants a code change made by Offload (a daemon on their GPU box where a local model does the typing and Claude plans and reviews), or asks to queue, check, answer, retry, cancel or review an Offload job, or to register a repository with Offload. Triggers - offload, "give this to offload", "queue a job", "offload status", "offload report".
---

# Offload: how a Claude session uses it

Offload is a daemon on the owner's GPU box. It takes a job spec, clones the repository on the box, plans with
Claude, executes step by step with a local model inside a sandbox (tests after every step), reviews with
Claude, commits once, pushes a branch `offload/<job id>` to the repository it was given, and writes
`REPORT.md`. The code never leaves the box. Only the report (a diff stat, the reviewer's notes, times, cost)
comes back. One job runs at a time. A job that waits for the owner, a rate limit or the budget is parked and
the next job runs.

## 0. Reach it

The command is `offload`. On the box it is installed. On a laptop it is the SSH wrapper `bin/offload-remote`
symlinked as `offload`; it reads the box's SSH name from `OFFLOAD_HOST` or from `~/.config/offload/host`.
Every path in a spec is a path **on the box**. A spec file must be on the box too (`scp` it first).

```bash
offload doctor          # Docker, sandbox image, proxy, token, budget: all [ok] means ready
offload status          # every job, its state, cost, last event
offload repo list       # the repositories Offload may work on
```

If `doctor` is not ready, stop and tell the user what is missing. Do not try to fix the box.

## 1. Register the repository once

```bash
offload repo add <path-or-url-reachable-from-the-box> "one line on what it is; tests are <command>"
```

`repo add` runs `git ls-remote` first and refuses a target the box cannot reach. Give the canonical
repository (a bare repository on the box, or a URL). The branch Offload pushes lands **there**. A clone
elsewhere sees it only after `git fetch <that remote>`.

## 2. Write the spec

The spec is what makes a job succeed. Write it with the repository in context. A job from a one-line request
goes through intake (one Claude call, no repository access) and fails more often. The template:

```markdown
---
title: <one line>
repo: <the registered path or URL>
test: <the test command, run after every step, for example python3 -m pytest -q tests>
allow_test_edits: true       # only for a refactor that must touch existing tests; leave out otherwise
---
## Goal
<Two to four sentences. What exists today, what must exist after, why.>

Requirements:
1. <One change per item. Name the file, the function, the key, the default, the exact message.>
2. <Order the items so that the tests pass after each one. A step that removes a name must update every user in the same step, or an earlier step must add the new name while the old one still works.>
3. <Tests: the file name and one line per test case.>

## Done when
- `<command>` passes with at least N tests
- `grep -rn "<old name>" src tests` prints nothing
- <one checkable line per requirement>
```

Rules that came from real failures:

- Every requirement names files. "Add a config key" fails; "`src/offload/config.py`: add `keep_days: int = 14` after `gate_wait_s`" succeeds.
- Keep one job under about 500 changed lines. Split larger work into jobs that each leave the tests green.
- A refactor needs `allow_test_edits: true`, or the worker cannot update test imports and every step fails.
- The local model does not run a linter. Say the line length and the lint command in the requirements, or run the linter on the branch before merging.
- Never put a secret, a host name, or a personal path in a spec. The spec is stored with the job and may be published as evidence.

## 3. Submit

```bash
scp spec.md <box>:/tmp/spec.md
offload add --spec /tmp/spec.md              # runs when its turn comes
offload add --spec /tmp/spec.md --confirm    # parks first; the owner answers `offload answer <job> yes`
offload add --confirm "one line"             # intake drafts a spec, posts it to the owner, waits for yes
```

`add` prints the job id. Use it for everything below.

## 4. Watch and answer

```bash
offload status                     # state: inbox, ready, running, waiting_owner, waiting_limit, waiting_budget, done, failed
offload log                        # the daemon's last 40 lines
offload report <job>               # REPORT.md: outcome, branch, diff stat, cost, decisions, steps
offload answer <job> yes           # a gate: publish, confirm, or "which repository"
offload cancel <job>               # stops a waiting job now, a running job before its next worker call
offload retry <job> [--replan] [--note "..."]   # a failed job again, without a second intake
offload cost                       # the week's Claude spend against the budget, per job
```

A limit or the budget parks the job; nothing to do. A `waiting_owner` job needs an answer. Cost figures are
API list-price equivalents drawn from the owner's subscription: a pacing unit, not a bill, unless the box
runs on an API key.

## 5. Review the branch before anyone merges it

The reviewer inside Offload approves or requests changes, and the report quotes it. That is not the last
word. On the box, or on any clone with the repository as a remote:

```bash
git fetch <remote> offload/<job id>
git diff --stat main...FETCH_HEAD
git diff main...FETCH_HEAD            # read it
<lint command>; <test command>
git merge --no-ff FETCH_HEAD
```

Reject a branch that does more than the spec asked. Two branches were rejected on this project for
deleting more than they were told to; the report said so, and reading the diff caught it.

## What Offload is not for

Open-ended design work, anything that needs the owner's judgement mid-way, changes across several
repositories, and anything under 20 lines (faster by hand). It is for precise, testable changes on a
registered repository, while the person does something else.
