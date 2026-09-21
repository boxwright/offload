# Report — a2-killed: Fix the failing statistics tests in the demo repository

**Outcome:** done  
**Branch:** `offload/a2-killed` on `~/.local/share/offload/demo-calc.git`  
**Change:**  1 file changed, 14 insertions(+), 2 deletions(-)  
**Cost (list-equivalent):** $0.13 opus $0.09, sonnet $0.04  
**Time:** local worker 45 s over 2 sessions; Claude 16 s over 2 calls  

## Decisions the engine made
- plan: 2 steps (planner claude/opus)
- review: APPROVE — APPROVE Tests pass (6/6), fix is minimal (mean divisor bug), only calc/__init__.py touched. The median rewrite is behaviorally identical to the original (just reformatted with docstring/comments), consistent with plan step 2's "re-check and document" framing.

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 7.8 s, 4 turns
- step 1: local/harness 16.6 s, 4 turns
- step 2: local/harness 28.4 s, 6 turns
- review: claude/sonnet 8.6 s, 3 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-20 17:06:39
