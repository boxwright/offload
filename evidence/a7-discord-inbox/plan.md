# Plan — a7-discord-inbox

Plan:

1. In `src/offload/config.py` add `discord_bot_token_file`, `discord_channel_id` and `discord_owner_id` to `Config` right after `webhook_file` with the specified comments, add the same three keys commented out (under the `# Answers from Discord: ...` comment) after the `webhook_file` line in `config.example.yaml`, and add `discord_bot_token_file=str(tmp_path / "discord-bot-token")` to the `settings` fixture in `tests/conftest.py`. (local-ok)
2. Add `src/offload/inbound.py` (stdlib only, module docstring) with `DISCORD_EPOCH_MS`, `snowflake_after`, `DiscordInbox.messages_after`/`acknowledge` (never raising, owner-only non-bot messages oldest first), `make_inbox` and `is_configured`, mirroring the request/timeout style of `src/offload/notifiers.py`. (hard)
3. Wire the read-only users: in `src/offload/notify.py` import `inbound` and make `ask_owner`'s posted message end with the "Reply here with yes or no…" sentence when `inbound.is_configured(get_config())` else the existing engine-host line; in `src/offload/setup_cmds.py` `doctor` print the `[ok] Discord inbox: channel …, owner …` / `[optional] Discord inbox not configured …` line after the notifier line; append the bot-token sentence to the "Three questions, ever" line in `README.md`. (local-ok)
4. In `src/offload/daemon.py` add `INBOUND_POLL_S = 30`, `_last_poll`, `_last_message_id`, `_open_gates(jobs_root)` and `_collect_answers(jobs_root, inbox)` (30 s throttle, snowflake floor from `deadline - gate_wait_s`, single-gate whole-text match, multi-gate job-id/unambiguous-prefix match, `answer_ignored` events on the oldest gate, then `jobs.answer` + `answer_from_chat` event + `acknowledge` + gate removal), and call it from `serve` inside a `try/except Exception` that prints with the `[{now()}]` prefix just before `picked = ...`, with `inbox = make_inbox(get_config())` built once before the loop. (hard)
5. Add `tests/test_inbound.py` covering snowflakes, `messages_after` headers/query/filtering/failure modes, `acknowledge`, `make_inbox` configuration cases, `_collect_answers` for one gate, two gates, the ambiguous message and the 30 s throttle, and `ask_owner`'s two sentences — using a threaded `http.server.HTTPServer` on `127.0.0.1:0` shaped like `tests/test_notifiers.py`, enough cases to bring the suite to at least 165 tests. (hard)

Test: `python3 -m pytest -q tests`

## Log
- step 1 done by local/harness in 302.2 s
- step 2 done by local/harness in 751.0 s
- step 3 done by local/harness in 225.4 s
- step 4 done by local/harness in 731.4 s
- step 5 done by local/harness in 797.8 s
