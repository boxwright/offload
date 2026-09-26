# Report — j20260924-082225: Run the spec checks before a job may report done

**Outcome:** done  
**Branch:** `offload/j20260924-082225` on `~/repos/offload.git`  
**Change:**  10 files changed, 461 insertions(+), 14 deletions(-)  
**Cost (list-equivalent):** $1.03 opus $0.83, sonnet $0.20  
**Time:** local worker 3412 s over 8 sessions; Claude 92 s over 2 calls  

## Decisions the engine made
- plan: 5 steps (planner claude/opus, 1 attempt)
- plan attempt 1: first attempt, max_turns 20
- review: APPROVE — All grep/Done-when criteria satisfied, and tests pass (115 passed).  APPROVE  Diff correctly adds the `checks:` front-matter key (inline + block list forms), raises `JobError` naming `checks` for malformed values, runs checks once via a shared `run_command` sandbox helper (same working dir, no netwo

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 65.2 s, 18 turns
- step 1: local/harness 1018.9 s, 37 turns
- step 2: local/harness 380.3 s, 24 turns
- step 3: local/harness 192.4 s, None turns
- step 1: local/harness 382.2 s, 25 turns
- step 2: local/harness 136.6 s, 12 turns
- step 3: local/harness 562.1 s, 33 turns
- step 4: local/harness 347.9 s, 25 turns
- step 5: local/harness 391.2 s, 27 turns
- review: claude/sonnet 27.1 s, 14 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-24 09:28:59
