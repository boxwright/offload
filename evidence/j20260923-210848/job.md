---
id: j20260923-210848
title: Add `offload retry <job>` to re-queue failed jobs reusing spec and plan
repo: ~/repos/offload.git
test: python3 -m pytest -q
branch: offload/j20260923-210848
tier: claude
gates: []
public: false
---
## Goal
Add a `retry` command to the offload CLI that re-queues an existing job by reusing its already-stored spec and plan, so neither intake nor planning is paid for again. The command accepts an optional `--note TEXT` whose content is appended to the step brief handed to the worker, and a `--replan` flag that discards the stored plan and re-runs planning while still skipping intake. Retrying a job that is not in a failed state must be refused with a clear, actionable message rather than silently re-queueing or crashing. Cover all three behaviours with tests.

## Done when
- `offload retry <job>` re-queues a failed job from its stored spec and plan with no second intake or planning call
- `--note TEXT` appends the note to the step brief and `--replan` re-runs planning (still skipping intake)
- retrying a job in any non-failed state exits non-zero with a clear message naming the job's current state
- tests exist for --note, --replan, and the non-failed refusal, and `python3 -m pytest -q` passes
