# Plan — a5-notifier

1. Add `src/offload/notifiers.py` (module docstring; `Notifier` base with `post` returning `(False, "no notifier configured")`, `DiscordNotifier(webhook_file)` moving today's `post_webhook` body verbatim, `NtfyNotifier(url, token_file="")` posting `text[:4000]` as UTF-8 bytes with `Content-Type: text/plain; charset=utf-8`, `Title: offload` and an optional `Authorization: Bearer <first line>`, and `make_notifier(config)` dispatching on `config.notifier` with a `ValueError` naming the bad value and the three allowed ones), using only `json`, `os`, `urllib.request`, `urllib.error`. (hard)
2. Add the `notifier`, `ntfy_url` and `ntfy_token_file` fields with their comments to the `Config` dataclass in `src/offload/config.py` right after `webhook_file`, and add the three commented-out keys plus the one-line explanatory comment to `config.example.yaml` after its `webhook_file` line. (local-ok)
3. In `src/offload/notify.py` delete `post_webhook`, add `def post(text)` returning `notifiers.make_notifier(get_config()).post(text)` with a one-sentence docstring and make `notify()` call it, drop the now-unused imports, and in the same step switch `src/offload/report.py` to import and call `post` in `digest` and switch the `quiet` fixture in `tests/test_parking.py` to patch `notify.post`. (hard)
4. Add `tests/test_notifiers.py` with a fixture running a daemon-thread `http.server.HTTPServer` on `127.0.0.1:0` that records `(path, headers, body)` per request and answers 200, covering Discord success/truncation/missing-webhook-file, ntfy success, ntfy with a `tok123\n` token file, ntfy against a closed port, `make_notifier` for all three values plus `ValueError` on `"slack"`, and `notify.post` routed through a config installed with `config.set_config`. (hard)
5. In `doctor` in `src/offload/setup_cmds.py` replace the webhook line with one that branches on `settings.notifier` (discord: today's `webhook_file` check; ntfy: `[ok]` when `ntfy_url` is set else `[optional] ntfy_url is empty`; none: `[optional] notifier: none`), keeping the trailing hint text, and reword the Discord line in the `README.md` feature list to say Discord or ntfy. (local-ok)

Test: `python3 -m pytest -q tests`

## Log
- step 1 done by local/harness in 268.9 s
- step 2 done by local/harness in 86.7 s
- step 3 done by local/harness in 280.0 s
- step 4 done by local/harness in 267.6 s
- step 5 done by local/harness in 787.2 s
