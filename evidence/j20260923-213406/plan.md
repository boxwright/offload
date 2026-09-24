# Plan — j20260923-213406

Repository read. Plan:

1. Add `plan_max_turns: int = 20` and `plan_reads: str = "full"` to the `Config` dataclass with a `full`/`index` validation in `load_config` (ValueError naming the bad value), document both keys in `config.example.yaml`, replace the hardcoded `max_turns=8` in `engine._plan` with `get_config().plan_max_turns`, and add tests in `tests/test_config.py` for the defaults, an override, and the rejected value. (local-ok)
2. Add an optional `tools=None` argument to `workers.claude` and `workers._call_claude` that falls back to `get_config().claude_tools`, plus a `plan_tools(config)` helper in `config.py` that returns `claude_tools` for full mode and the same list without `Read` and `Bash(cat *)` for index mode, with tests covering both the fallback and the stripped tool list. (local-ok)
3. Make `engine._plan` honour `plan_reads`: in index mode pass a `git ls-files` file tree into a new optional `tree` argument of `prompts.plan_prompt` (unchanged prompt text when it is absent) and call `claude(..., tools=plan_tools(get_config()))`, updating the `Fakes.claude` stand-in in `tests/test_parking.py` for the new argument, and add tests that full mode sends today's prompt and tools while index mode sends the tree and neither `Read` nor `Bash(cat *)`. (hard)
4. Write `docs/design/plan-reads.md` with the token and turn evidence (88k–213k tokens of context on engine-src, the 8-turn exhaustion at 42 cents versus 4–5 turns on the demo repo), a description of both modes and their tool sets, how to measure plan quality by re-running `calibration/run_claude.sh` plus `calibration/score.py` over `calibration/tasks` and comparing turns and pass rate, and the rollback procedure of setting `plan_reads: full` and raising `plan_max_turns`, linked from `README.md` or `DESIGN.md` so the doc is reachable. (hard)

Test: python3 -m pytest -q tests

## Log
- step 1 done by local/harness in 270.8 s
- step 2 done by local/harness in 1034.6 s
- step 3 done by local/harness in 860.9 s
- step 4 done by local/harness in 293.0 s
