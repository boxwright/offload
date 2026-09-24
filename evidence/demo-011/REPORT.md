# Report — demo-011: Fix the failing statistics tests in the demo repository

**Outcome:** done  
**Branch:** `offload/demo-011` on `~/.local/share/offload/demo-calc.git`  
**Change:**  1 file changed, 10 insertions(+), 1 deletion(-)  
**Cost (list-equivalent):** $0.13 opus $0.10, sonnet $0.03  
**Time:** local worker 39 s over 2 sessions; Claude 15 s over 2 calls  

## Decisions the engine made
- plan: 2 steps (planner claude/opus, 1 attempt)
- plan attempt 1: first attempt, max_turns 20
- review: APPROVE — Diff only touches `calc/__init__.py`, fixes the off-by-one divisor bug, tests weren't modified, and all 6 tests pass.  APPROVE - Fix is correct and minimal: `len(xs) - 1` → `len(xs)`. - Scope respects "touches only `calc/`" constraint. - Added docstrings are harmless and match the stated plan. - `py

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 10.3 s, 5 turns
- step 1: local/harness 20.6 s, 5 turns
- step 2: local/harness 18.0 s, 4 turns
- review: claude/sonnet 4.8 s, 2 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-24 06:38:15
