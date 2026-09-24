# Plan — j20260923-213813

1. Add the plan-recovery knobs alongside the rescue ones: a `max_plan_attempts: 2` key under `claude.per_job` in `budget.yaml` and `templates.DEFAULT_BUDGET`, a `plan_attempts()` reader in `src/offload/budget.py` defaulting to 2, and a narrowed `plan_retry_prompt(job)` in `src/offload/prompts.py` that asks only for the numbered steps and the `Test:` line. (local-ok)
2. Rewrite `_plan` in `src/offload/engine.py` as an escalating ladder: attempt 1 is today's call (`plan_prompt`, max_turns=8); when it yields no steps or the meta says the run ended on max_turns, retry through the same `claude(...)` helper with a larger turn budget, then with `plan_retry_prompt`, emitting a `plan_attempt` event per attempt carrying attempt number, escalation reason and max_turns, and only failing with "no plan steps" once `plan_attempts()` attempts are spent. (hard)
3. Surface recovery in `src/offload/report.py`: add `plan_attempt` lines to `_decision_lines`, note the attempt count on the report's plan line so a self-rescued job differs from a clean run, and add a plan-recovery count to `digest`. (local-ok)
4. Add `tests/test_plan_recovery.py` with a fake `engine.claude` that records prompts/max_turns per call, covering recovery on the first retry, recovery on the narrowed second retry, exhaustion failing with "no plan steps" and EXIT_SETUP, the cap being read from the budget file, and the `plan_attempt` events reaching REPORT.md. (hard)

Test: python3 -m pytest -q

## Log
- step 1 done by local/harness in 397.9 s
- step 2 done by local/harness in 375.4 s
- step 3 done by local/harness in 515.1 s
- step 4 done by local/harness in 1200.0 s
