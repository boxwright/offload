# Report — j20260923-210848: Add `offload retry <job>` to re-queue failed jobs reusing spec and plan

**Outcome:** done  
**Branch:** `offload/j20260923-210848` on `~/repos/offload.git`  
**Change:**  7 files changed, 179 insertions(+), 2 deletions(-)  
**Cost (list-equivalent):** $0.81 opus $0.55, sonnet $0.26  
**Time:** local worker 1676 s over 5 sessions; Claude 82 s over 3 calls  

## Decisions the engine made
- plan: 5 steps (planner claude/opus)
- review: APPROVE — APPROVE  Implementation correctly reuses stored spec/plan: `job.md`/`intake.json` are untouched so `Job.repo` stays set and the daemon skips intake; `plan.txt` (which gates re-planning in `engine._plan`) is deleted only under `--replan`. `note.txt` is threaded into `step_brief` correctly, and the no

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 10.6 s, 1 turns
- plan: claude/opus 38.8 s, 16 turns
- step 1: local/harness 288.2 s, 25 turns
- step 2: local/harness 427.0 s, 41 turns
- step 3: local/harness 139.4 s, 20 turns
- step 4: local/harness 735.1 s, 40 turns
- step 5: local/harness 86.1 s, 14 turns
- review: claude/sonnet 33.0 s, 18 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-23 22:48:06
