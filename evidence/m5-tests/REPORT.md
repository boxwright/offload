# Report — m5-tests: Add a pytest suite for the engine's pure logic

**Outcome:** done  
**Branch:** `engine/m5-tests` on `~/repos/offload.git`  
**Change:**  6 files changed, 446 insertions(+), 1 deletion(-)  
**Cost (list-equivalent):** $0.53 opus $0.40, sonnet $0.13  
**Time:** local worker 740 s over 7 sessions; Claude 36 s over 2 calls  

## Decisions the engine made
- plan: 6 steps (planner claude/opus)
- review: APPROVE — APPROVE  Tests pass (33/33, ≥18 required). `engined.py` diff is exactly the requested `is_stuck` extraction with unchanged behavior. All tests use `tmp_path`/`monkeypatch` for `LEDGER`/`BUDGET_FILE`/job dirs, explicit `now` values — no network, Docker, or real-home access. Time/budget/job coverage m

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 19.1 s, 5 turns
- step 1: qwen/hermes 106.6 s, 42 (1 user, 39 tool calls)
- step 1: qwen/hermes 81.9 s, 19 (1 user, 16 tool calls)
- step 2: qwen/hermes 159.2 s, 32 (1 user, 29 tool calls)
- step 3: qwen/hermes 101.9 s, 30 (1 user, 26 tool calls)
- step 4: qwen/hermes 171.7 s, 38 (1 user, 35 tool calls)
- step 5: qwen/hermes 90.6 s, 22 (1 user, 19 tool calls)
- step 6: qwen/hermes 28.0 s, 21 (1 user, 19 tool calls)
- review: claude/sonnet 17.3 s, 10 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-17 08:17:38
