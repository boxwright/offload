---
id: a7-discord-inbox
title: Answer a gate from Discord: poll the channel with a bot token while a job waits for the owner
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: offload/a7-discord-inbox
allow_test_edits: true
---
## Goal
Today a gate posts its question through the Discord webhook, and the owner must answer on the host with `offload answer <job> yes`. Add an inbound path: while at least one job is `waiting_owner`, the daemon polls the Discord channel every 30 seconds through the REST API with a bot token, accepts a reply from the owner's user id only, writes it as the job's answer, and reacts to the message with a check mark. Nothing listens on the network; the daemon makes outbound GET and PUT requests only, and only while a gate is open. When no bot token is configured, nothing changes.

Requirements:

1. `src/offload/config.py`: add to `Config` after `webhook_file`:
   - `discord_bot_token_file: str = _in(config_dir, "discord-bot-token")` with the comment `# optional; enables answers from the channel; chmod 600`
   - `discord_channel_id: str = ""` with the comment `# the channel the webhook posts to`
   - `discord_owner_id: str = ""` with the comment `# the owner's Discord user id; replies from anyone else are ignored`
   Add the three keys, commented out, to `config.example.yaml` after the `webhook_file` line with one comment line above them: `# Answers from Discord: a bot token (Read Message History, Add Reactions, Message Content intent), the channel, and your user id.`
   Add `discord_bot_token_file=str(tmp_path / "discord-bot-token")` to the `settings` fixture in `tests/conftest.py`.

2. New module `src/offload/inbound.py` (standard library only: `json`, `os`, `time`, `urllib.parse`, `urllib.request`, `urllib.error`) with a module docstring and:
   - `DISCORD_EPOCH_MS = 1420070400000` and `def snowflake_after(epoch_seconds)`: the Discord snowflake for that moment, `(int(epoch_seconds * 1000) - DISCORD_EPOCH_MS) << 22`, as an int; a moment before the Discord epoch returns 0.
   - `class DiscordInbox` with `__init__(self, token, channel_id, owner_id, api="https://discord.com/api/v10")`.
     - `messages_after(self, after_id)`: GET `{api}/channels/{channel_id}/messages?after={after_id}&limit=50` with headers `Authorization: Bot {token}` and `User-Agent: offload/0.1`, timeout 20 s. Returns a list of dicts `{"id": str, "text": str, "ts": str}` for messages whose `author.id` equals `owner_id` and whose `author.bot` is not true, oldest first (Discord returns newest first: reverse it). On any `urllib.error.URLError`, `OSError`, `ValueError` or a body that is not a list, return `[]`. Never raise.
     - `acknowledge(self, message_id)`: PUT `{api}/channels/{channel_id}/messages/{message_id}/reactions/%E2%9C%85/@me` with the same headers and an empty body. Returns True on HTTP 2xx, False otherwise. Never raise.
   - `def make_inbox(config)`: returns a `DiscordInbox` when `config.notifier == "discord"`, `config.discord_channel_id` and `config.discord_owner_id` are non-empty, and `config.discord_bot_token_file` exists (token = the file's first line, stripped). Otherwise `None`.
   - `def is_configured(config)`: True when `make_inbox(config)` would return an inbox, without reading the token.

3. `src/offload/notify.py`, in `ask_owner`: the message posted to the owner ends with `Reply here with yes or no. Start with the job id when more than one job is waiting.` when `inbound.is_configured(get_config())` is true, else with the existing `Reply on the engine host: ...` line. Import `inbound` at the top of the module.

4. `src/offload/daemon.py`:
   - `INBOUND_POLL_S = 30`, module variables `_last_poll = 0.0` and `_last_message_id = 0` (an int; the largest message id seen).
   - `def _open_gates(jobs_root)`: the list of `(job_dir, record)` for jobs whose status is `waiting_owner` and whose `answer.txt` does not exist, oldest job name first.
   - `def _collect_answers(jobs_root, inbox)`: returns the number of answers written. Returns 0 at once when `inbox` is None, when no gate is open, or when fewer than `INBOUND_POLL_S` seconds passed since `_last_poll`. Otherwise sets `_last_poll`, computes `after = max(_last_message_id, snowflake_after(asked))` where `asked` is the smallest `record["deadline"] - get_config().gate_wait_s` over the open gates, and calls `inbox.messages_after(after)`. For each message, oldest first: update `_last_message_id` to `max(_last_message_id, int(message["id"]))`; choose the job: with exactly one open gate, the whole text is the answer; with more than one, the text must start with a job id (the directory name) or an unambiguous prefix of one, followed by a space or the end of the text, and the rest is the answer; a message that matches no job or more than one is logged with `Job(job_dir).event("answer_ignored", message_id=..., reason="ambiguous"|"no job id")` on the oldest open gate's job and skipped. For a matched job: `jobs.answer(job_dir, answer_text)` (this writes `answer.txt`), `Job(job_dir).event("answer_from_chat", message_id=message["id"], text=answer_text[:200])`, `inbox.acknowledge(message["id"])`, and remove that gate from the open list so a second message goes to the next job.
   - In `serve`: build `inbox = make_inbox(get_config())` once before the loop; in the loop, right before `picked = ...`, call `_collect_answers(jobs_root, inbox)` inside a `try/except Exception` that prints the error with the `[{now()}]` prefix (the inbox must never stop the loop).

5. `src/offload/setup_cmds.py`, in `doctor`, after the notifier line: print `  [ok] Discord inbox: channel {id}, owner {id}` when `inbound.is_configured(settings)`, else `  [optional] Discord inbox not configured — answers by \`offload answer\` on the host`.

6. New file `tests/test_inbound.py` with a fake `http.server.HTTPServer` on `127.0.0.1` port 0 in a daemon thread (the same shape as `tests/test_notifiers.py`): the handler records `(method, path, headers, body)` and answers GET with a JSON list set by the test, PUT with 204. Tests:
   - `snowflake_after(1420070400) == 0`, `snowflake_after(1420070401) == 1000 << 22`, `snowflake_after(0) == 0`.
   - `messages_after` sends `Authorization: Bot tok`, requests `after=<id>&limit=50`, returns only the owner's non-bot messages, oldest first, as `{"id","text","ts"}`.
   - `messages_after` against a closed port returns `[]` and does not raise; a non-list body returns `[]`.
   - `acknowledge` PUTs `/channels/<c>/messages/<m>/reactions/%E2%9C%85/@me` and returns True.
   - `make_inbox` returns None without a token file, without ids, and with `notifier: ntfy`; returns an inbox when all three are set (use `dataclasses.replace(settings, ...)` and write the token file).
   - `_collect_answers` with a fake inbox object (a class with `messages_after` returning a fixed list and `acknowledge` recording ids): one open gate → `answer.txt` holds the text, an `answer_from_chat` event exists, the message was acknowledged; two open gates → `a-first yes` goes to `a-first`, `b-second no` goes to `b-second`, and `maybe` with two gates open is ignored with an `answer_ignored` event; a second call within 30 s makes no request (set `daemon._last_poll` and `daemon._last_message_id` explicitly at the start of each test).
   - `ask_owner` posts the "Reply here" sentence when the inbox is configured and the "engine host" sentence when it is not (patch `notify.post` to capture the text).

7. `README.md`: in the "Three questions, ever" feature line, append: ` Configure a bot token and it takes your answer from the Discord channel too.`

## Done when
- `python3 -m pytest -q tests` passes with at least 165 tests.
- `grep -rn "discord.com" src` prints only lines in `src/offload/inbound.py`.
- `ruff check src tests` prints "All checks passed!" (line length 120; run it with `python3 -m ruff check src tests` if `ruff` is not on PATH, and if ruff is not installed, keep every line under 120 characters and imports sorted).
- With no config file, `python3 -m offload doctor 2>&1 | grep -c "Discord inbox not configured"` prints 1.
