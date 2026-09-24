---
id: j20260923-213813
title: Add escalating plan-recovery ladder so no-step plan calls retry instead of failing terminally
repo: ~/repos/offload.git
test: python3 -m pytest -q
branch: offload/j20260923-213813
tier: claude
gates: ["money"]
public: false
---
## Goal
Today an offload plan call that returns no usable steps (or ends on max_turns) fails the whole job terminally with reason "no plan steps", burning spend for no output. Steps already have a rescue ladder governed by max_rescues in the budget file; plan has no equivalent. Add a plan recovery ladder in the same idiom: on no steps or a max_turns finish, retry first with a larger turn budget, then with a narrower prompt that asks only for the numbered steps and the test line, capped by a new budget-file setting alongside max_rescues (default 2), failing only once the ladder is exhausted. Each attempt is recorded as its own event carrying the escalation reason, and offload report surfaces that a job needed plan recovery and how many attempts it took.

## Done when
- A plan call returning no steps or ending on max_turns triggers retry with a larger turn budget, then a narrowed steps-and-test-line-only prompt, and fails with "no plan steps" only after the configured cap is exhausted
- The attempt cap is read from a new key in the budget file next to max_rescues, defaulting to 2, and each attempt emits its own event recording the reason it escalated
- offload report shows plan-recovery occurred for a job and the number of attempts, so a self-rescued job is distinguishable from a clean run
- Recovery attempts go through the same budget pacing and rate-limit parking path as other Claude calls, and new tests cover recovery on the first retry, recovery on the second, and ladder exhaustion
