# Report — demo-008: Fix the failing statistics tests in the demo repository

**Outcome:** done  
**Branch:** `offload/demo-008` on `~/.local/share/offload/demo-calc.git`  
**Change:**  1 file changed, 10 insertions(+), 1 deletion(-)  
**Cost (list-equivalent):** $0.18 opus $0.12, sonnet $0.05  
**Time:** local worker 36 s over 2 sessions; Claude 22 s over 2 calls  

## Decisions the engine made
- plan: 2 steps (planner claude/opus)
- review: APPROVE — Tests pass, diff only touches `calc/__init__.py`, fix is correct (divide by `len(xs)` instead of `len(xs)-1`), tests unmodified, docstrings are harmless additions.  APPROVE - All 6 tests pass; fix matches the confirmed defect. - Change scoped to `calc/` only, as required. - Docstring additions are i

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 17.8 s, 5 turns
- step 1: local/harness 17.9 s, 4 turns
- step 2: local/harness 18.5 s, 4 turns
- review: claude/sonnet 4.1 s, 2 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-23 05:57:12
