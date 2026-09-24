---
id: j20260923-213406
title: Make plan turn budget configurable (default 20) and add plan_reads full/index mode
repo: ~/repos/offload.git
test: python -m pytest
branch: offload/j20260923-213406
tier: claude
gates: ["money"]
public: false
---
## Goal
The plan step in the offload engine is the least reliable step: on engine-src it reads 88k-213k tokens of repository context and has the tightest turn budget in the engine (8) while carrying the broadest instruction ("read this repository"), and at least one job exhausted max_turns at 8 turns and failed with zero plan steps after spending 42 cents, versus 4-5 turns for the same step on the small demo repo. Make the plan turn budget a configuration value with a new default of 20, and add a plan_reads setting with modes full (exactly today's behaviour) and index (file tree plus job spec, Glob and Grep available, no Read and no cat tool), defaulting to full so nothing changes until it is deliberately switched on. Document the evidence, both modes, how to measure plan quality against the calibration harness, and the rollback path in docs/design/plan-reads.md.

## Done when
- Plan turn budget is read from configuration with a default of 20 and no hardcoded 8 remains in the plan step
- plan_reads config setting accepts full and index, defaults to full, and index mode gives the planner a file tree plus job spec with Glob and Grep but no Read and no cat tool
- docs/design/plan-reads.md records the token and turn evidence, describes both modes, explains how to measure plan quality with the calibration harness, and states the rollback procedure (set plan_reads back to full and raise the turn budget further)
- Tests cover the configurable turn budget, full mode, and index mode tool restrictions, and the full test suite passes
