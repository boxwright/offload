# Calibration results

Five pytest-scored tasks (`tasks/`): implement from spec, fix a buggy module,
write a CLI, refactor duplication, implement an LRU. Scoring: tests pass and
the test files are byte-identical to the originals.

## 2026-09-16 — Qwen3.8-27B via Hermes CLI on the GPU box (`--yolo --reasoning low`, fresh session per task)

| Task | Pass | Wall | Messages | Container peak after | Error lines |
|---|---|---|---|---|---|
| t1 slugify | yes | 20.0 s | 9 (7 tool calls) | 31.01 GiB | 0 |
| t2 daterange bug | yes | 14.2 s | 10 (8) | 31.01 GiB | 0 |
| t3 wordfreq CLI | yes | 27.5 s | 12 (10) | 31.03 GiB | 0 |
| t4 refactor report | yes | 11.2 s | 9 (7) | 31.42 GiB | 0 |
| t5 LRU | yes | 16.5 s | 11 (9) | 31.42 GiB | 0 |

**5/5. 89 s total.** A first pass run by mistake without pytest on the box
(the worker could not check its work) also scored 5/5 when scored afterwards.
Raw lines: `results-qwen-hermes-2026-09-16.jsonl`.

Caveat: these are small, self-contained, well-specified tasks. They measure
"can the local model do clean mechanical coding with tools" and say nothing
yet about multi-file repos, ambiguous specs, or long jobs. Those come from the
loop's own records after M1.

## 2026-09-16 — Claude Sonnet 5, headless on the GPU box (`claude -p --permission-mode acceptEdits`, fresh session per task)

| Task | Pass | Wall | Turns | Cache-read tokens | Output tokens |
|---|---|---|---|---|---|
| t1 slugify | yes | 7.8 s | 5 | 132,013 | 725 |
| t2 daterange bug | yes | 16.3 s | 7 | 190,663 | 989 |
| t3 wordfreq CLI | yes | 17.9 s | 7 | 191,857 | 1,027 |
| t4 refactor report | yes | 22.3 s | 7 | 161,566 | 877 |
| t5 LRU | yes | 8.9 s | 6 | 161,505 | 755 |

**5/5. 73 s total.** Note: `acceptEdits` mode did not let it run pytest ("requires
your approval"), so Sonnet also wrote its code without running the tests, and
still passed. Raw lines: `results-claude-sonnet-2026-09-16.jsonl`.

## Read-out

- On small, well-specified tasks the two are equivalent on correctness (5/5
  each) and speed (Qwen 89 s, Sonnet 73 s for the set). The claim that the local model codes near
  Claude's level holds at this size.
- **Cost is the difference.** Each Sonnet task read 130k-190k cached tokens
  against the plan window (the harness prompt plus tools, re-read every turn).
  Qwen's cost was zero and the container stayed at 31 GiB.
- So the split in DESIGN.md is right for this class of work: Qwen executes,
  Claude plans and reviews. What is still unmeasured: multi-file repos,
  ambiguous specs, long jobs. The loop's own records after M1 answer those.

## 2026-09-17 — Qwen3.8-27B via Claude Code's harness (proxy + system-hoist hook), fresh session per task

| Task | Pass | Wall | Turns |
|---|---|---|---|
| t1 slugify | yes | 81.7 s | 26 (hit the 25-turn cap) |
| t2 daterange bug | yes | 73.1 s | 19 |
| t3 wordfreq CLI | yes | 91.2 s | 18 |
| t4 refactor report | yes | 24.1 s | 8 |
| t5 LRU | yes | 63.1 s | 26 (cap) |

**5/5. 333 s total**, against 89 s for the same model under the Hermes harness. The extra time is
mostly wasted turns: this runner uses `acceptEdits`, which blocks every `python3` call, and the model
kept retrying ("Every Python execution is blocked by the permission system"). The engine's worker uses
`dontAsk` plus an allowlist that includes pytest, so the fair comparison is still to run (P2).
Also in play: Claude Code's system prompt and 21 tool definitions are a much larger prefix than Hermes sends.
Raw lines: `results-qwen-harness-2026-09-17.jsonl`.

## 2026-09-23 — Qwen3.8-27B through the shipped path: Claude Code's harness inside the Offload sandbox, via the proxy (`run_harness.sh`)

| Task | Pass | Wall | Turns | Output tokens |
|---|---|---|---|---|
| t1 slugify | yes | 18.5 s | 8 | 1,588 |
| t2 daterange bug | yes | 14.7 s | 9 | 980 |
| t3 wordfreq CLI | yes | 20.3 s | 8 | 1,568 |
| t4 refactor report | yes | 12.7 s | 6 | 999 |
| t5 LRU | yes | 9.3 s | 7 | 540 |

**5/5. 75.5 s total.** Same model and box as the 2026-09-16 runs, now through the exact path a job uses (sandbox with
the firewall, `dontAsk` with the job tool list, the LiteLLM proxy, the container caps). Scored inside a no-network
container, because the host Python has no pytest. This is the baseline for any second model. Raw lines:
`results-qwen3.8-harness-sandbox-2026-09-23.jsonl`.
