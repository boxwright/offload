# Report — m5-config: Move every machine-specific constant into a config file with safe defaults

**Outcome:** done  
**Branch:** `engine/m5-config` on `~/repos/offload.git`  
**Change:**  4 files changed, 423 insertions(+), 30 deletions(-)  
**Cost (list-equivalent):** $0.47 opus $0.23, sonnet $0.24  
**Time:** local worker 868 s over 5 sessions; Claude 68 s over 2 calls  

## Decisions the engine made
- plan: 5 steps (planner claude/opus)
- review: APPROVE — APPROVE  Tests pass (45, ≥40 floor), the forbidden literals are gone from `engined.py`, and `python3 engined/engined.py budget` still works with no config file present. Two minor, non-blocking notes: - `config.py` silently falls back to a hand-rolled flat YAML parser when PyYAML is missing, rather t

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 32.3 s, 7 turns
- step 1: qwen/hermes 394.3 s, \s*(.+)", out); s = re.search(r"Session:\s*(\S+)", out)
- step 2: qwen/hermes 107.6 s, 24 (1 user, 22 tool calls)
- step 3: qwen/hermes 147.7 s, 36 (1 user, 32 tool calls)
- step 4: qwen/hermes 201.8 s, 38 (1 user, 35 tool calls)
- step 5: qwen/hermes 16.5 s, 12 (1 user, 10 tool calls)
- review: claude/sonnet 35.8 s, 13 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-17 08:34:35
