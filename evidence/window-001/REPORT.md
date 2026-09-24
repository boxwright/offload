# Report — window-001: Fix the failing statistics tests in the demo repository

**Outcome:** done  
**Branch:** `offload/window-001` on `~/.local/share/offload/demo-calc.git`  
**Change:**  1 file changed, 9 insertions(+), 1 deletion(-)  
**Cost (list-equivalent):** $0.15 opus $0.10, sonnet $0.05  
**Time:** local worker 34 s over 2 sessions; Claude 20 s over 2 calls  

## Decisions the engine made
- plan: 2 steps (planner claude/opus, 1 attempt)
- review: APPROVE — APPROVE Fix correctly changes `len(xs) - 1` to `len(xs)` in `mean`; docstrings added to `mean`/`median` with no behavior change. Diff touches only `calc/__init__.py`, tests weren't modified, and `python3 -m pytest -q` passes (6 passed).

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 11.0 s, 5 turns
- step 1: local/harness 13.6 s, 5 turns
- step 2: local/harness 20.2 s, 8 turns
- review: claude/sonnet 8.8 s, 2 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-24 08:59:02
