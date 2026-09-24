# Report — j20260923-213406: Make plan turn budget configurable (default 20) and add plan_reads full/index mode

**Outcome:** done  
**Branch:** `offload/j20260923-213406` on `~/repos/offload.git`  
**Change:**  11 files changed, 390 insertions(+), 17 deletions(-)  
**Cost (list-equivalent):** $1.27 opus $1.10, sonnet $0.17  
**Time:** local worker 2459 s over 4 sessions; Claude 113 s over 4 calls  

## Decisions the engine made
- plan: 4 steps (planner claude/opus, 1 attempt)
- plan attempt 1: first attempt, max_turns 20
- review: APPROVE — APPROVE Turn budget now reads `plan_max_turns` (default 20, no hardcoded 8 remains), `plan_reads` validates full/index with a naming ValueError, and index mode correctly strips `Read`/`Bash(cat *)` while keeping `Glob`/`Grep`. `plan_prompt` swaps in the file tree only when given one, leaving full mo

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 12.4 s, 1 turns
- plan: claude/opus 40.3 s, 9 turns
- plan: claude/opus 45.5 s, 15 turns
- step 1: local/harness 270.8 s, 32 turns
- step 2: local/harness 1034.6 s, 44 turns
- step 3: local/harness 860.9 s, 41 turns
- step 4: local/harness 293.0 s, 35 turns
- review: claude/sonnet 14.9 s, 9 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-24 06:33:40
