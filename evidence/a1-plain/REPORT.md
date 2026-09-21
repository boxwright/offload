# Report — a1-plain: Fix the failing statistics tests in the demo repository

**Outcome:** done  
**Branch:** `offload/a1-plain` on `~/.local/share/offload/demo-calc.git`  
**Change:**  1 file changed, 2 insertions(+), 1 deletion(-)  
**Cost (list-equivalent):** $0.12 opus $0.08, sonnet $0.03  
**Time:** local worker 34 s over 2 sessions; Claude 14 s over 2 calls  

## Decisions the engine made
- plan: 2 steps (planner claude/opus)
- review: APPROVE — APPROVE  Fix is correct and minimal: `mean` now divides by `len(xs)`, all 6 tests pass, and only `calc/__init__.py` was touched. Minor nit: the plan mentioned adding a docstring to both `mean` and `median`, but only `median` got one — not a functional issue.

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 7.9 s, 4 turns
- step 1: local/harness 16.4 s, 4 turns
- step 2: local/harness 17.6 s, 5 turns
- review: claude/sonnet 6.2 s, 2 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-20 17:03:47
