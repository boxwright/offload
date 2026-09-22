# Report — a3-cleanup: Sweep old job folders and rotate the ledger monthly

**Outcome:** done  
**Branch:** `offload/a3-cleanup` on `~/repos/offload.git`  
**Change:**  8 files changed, 366 insertions(+), 2 deletions(-)  
**Cost (list-equivalent):** $0.57 opus $0.35, sonnet $0.22  
**Time:** local worker 1899 s over 6 sessions; Claude 86 s over 2 calls  

## Decisions the engine made
- plan: 6 steps (planner claude/opus)
- review: APPROVE — APPROVE — no.  REQUEST_CHANGES  - `sweep_finished_jobs` calls `shutil.rmtree(job_dir)` on the whole job directory, not just `work/`, `claude-home/`, `scratch/` — deletes `job.md`/`events.jsonl`/status itself, and never sets a `swept` field (dedup works only because the dir is gone). Directly contrad

## Decisions the owner made
- none needed

## Steps
- plan: claude/opus 22.5 s, 12 turns
- step 1: local/harness 100.5 s, 17 turns
- step 2: local/harness 967.7 s, 40 turns
- step 3: local/harness 233.3 s, 27 turns
- step 4: local/harness 168.2 s, 18 turns
- step 5: local/harness 62.5 s, 11 turns
- step 6: local/harness 367.2 s, 32 turns
- review: claude/sonnet 64.0 s, 10 turns

Plan: `plan.md` · Events: `events.jsonl` · Generated 2026-09-20 17:46:49
