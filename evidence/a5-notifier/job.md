---
id: a5-notifier
title: Put the Discord webhook behind a notifier interface and add an ntfy notifier
repo: ~/repos/offload.git
test: python3 -m pytest -q tests
branch: offload/a5-notifier
allow_test_edits: true
---
## Goal
`src/offload/notify.py` posts to a Discord webhook and nothing else. Put the posting behind one small interface, keep Discord as one implementation, and add a second: ntfy (https://ntfy.sh or a self-hosted server). The notifier is chosen in the config. Every existing caller (`notify`, `ask_owner`, the digest in `report.py`) keeps working unchanged. Owners with today's config (a `webhook_file`) must not have to change anything.

Requirements:

1. New module `src/offload/notifiers.py` with a module docstring and:
   - `class Notifier`: a base class with one method `post(self, text)` that returns `(ok, detail)` and never raises. The base `post` returns `(False, "no notifier configured")`. Docstring on the class: what a notifier is and the contract of `post` (returns a tuple, never raises, `text` may be longer than the service allows and the notifier truncates it).
   - `class DiscordNotifier(Notifier)`: `__init__(self, webhook_file)`. `post` reads the webhook URL from the file (missing file: `(False, "no webhook file")`), sends `{"content": text[:1900], "username": "offload"}` as JSON with `Content-Type: application/json` and `User-Agent: offload/0.1`, timeout 20 s, and returns `(True, response.status)` on success, `(False, str(exc)[:120])` on `urllib.error.URLError`, `OSError` or `ValueError`. This is exactly what `post_webhook` does today: move that code here.
   - `class NtfyNotifier(Notifier)`: `__init__(self, url, token_file="")`. `url` is the full topic URL, for example `https://ntfy.sh/my-offload-topic`. `post` sends `text[:4000]` as the request body (bytes, UTF-8) with `Content-Type: text/plain; charset=utf-8`, header `Title: offload`, and, when `token_file` is set and the file exists, `Authorization: Bearer <the file's first line, stripped>`. Same timeout, return values and exception handling as Discord. A missing token file is not an error: the request goes without the header.
   - `def make_notifier(config)`: returns `NtfyNotifier(config.ntfy_url, config.ntfy_token_file)` when `config.notifier == "ntfy"`, `DiscordNotifier(config.webhook_file)` when it is `"discord"`, and `Notifier()` when it is `"none"`. Any other value raises `ValueError` naming the value and the three allowed ones.
   - Use only the standard library (`json`, `os`, `urllib.request`, `urllib.error`).

2. `src/offload/config.py`: add to the `Config` dataclass, after `webhook_file`:
   - `notifier: str = "discord"` with the comment `# discord (webhook_file), ntfy (ntfy_url, ntfy_token_file), or none`
   - `ntfy_url: str = ""` with the comment `# the full topic URL, for example https://ntfy.sh/<topic>`
   - `ntfy_token_file: str = _in(config_dir, "ntfy-token")` with the comment `# optional; chmod 600`
   Add the three keys, commented out with their defaults, to `config.example.yaml` after the `webhook_file` line, with one comment line above them: `# Where messages go. discord needs webhook_file; ntfy needs ntfy_url and, for a protected topic, ntfy_token_file.`

3. `src/offload/notify.py`: delete `post_webhook`. Add `def post(text)` that does `return notifiers.make_notifier(get_config()).post(text)`; docstring one sentence. `notify()` calls `post` instead of `post_webhook`. Nothing else in the module changes.

4. `src/offload/report.py`: import `post` instead of `post_webhook` and call it in `digest`.

5. `src/offload/setup_cmds.py`, in `doctor`: replace the webhook line with one that reports the configured notifier: for `discord`, the existing check on `settings.webhook_file`; for `ntfy`, `[ok]` when `settings.ntfy_url` is not empty, else `[optional] ntfy_url is empty`; for `none`, `[optional] notifier: none`. The trailing hint text stays: ` — without it, gate questions only appear in \`offload status\``.

6. `tests/test_parking.py`: the autouse fixture `quiet` patches `notify.post_webhook`. Change it to patch `notify.post` with the same lambda.

7. New file `tests/test_notifiers.py`. Tests run against a fake server: a `http.server.HTTPServer` on `127.0.0.1` port 0, started in a `threading.Thread` (daemon) inside a fixture that yields the base URL and a list where the handler appends `(path, headers dict, body bytes)` for each request, then shuts the server down. The handler answers 200 with an empty body. Tests:
   - Discord: a webhook file with the fake URL; `post("hello")` returns `(True, 200)`; the request body is JSON with `content == "hello"` and `username == "offload"`; the `Content-Type` header is `application/json`.
   - Discord truncates: a 3000-character text arrives as 1900 characters of `content`.
   - Discord with no webhook file returns `(False, "no webhook file")`.
   - ntfy: `post("hello")` returns `(True, 200)`; the body is `b"hello"`; the `Title` header is `offload`; no `Authorization` header when there is no token file.
   - ntfy with a token file containing `tok123\n` sends `Authorization: Bearer tok123`.
   - ntfy against a closed port (open a socket, read its port, close it, use that port) returns `(False, <something>)` and does not raise.
   - `make_notifier` returns the right class for each of the three values (build a `Config` with `dataclasses.replace(Config(), notifier=..., ...)`) and raises `ValueError` for `"slack"`.
   - `notify.post` uses the configured notifier: with the `settings` fixture from `conftest` replaced by `dataclasses.replace(settings, notifier="ntfy", ntfy_url=<fake url>)` installed through `config.set_config`, `notify.post("x")` reaches the fake server. Restore the previous config at the end.

8. `README.md`: in the feature list, find the line that mentions Discord (`grep -n Discord README.md`) and change "Discord" so that the sentence says the message goes to Discord or ntfy. Keep the rest of the line. `docs/faq.md`: no change.

## Done when
- `python3 -m pytest -q tests` passes with at least 102 tests.
- `grep -rn "post_webhook" src tests` prints nothing.
- `grep -n "^import\|^from" src/offload/notifiers.py` shows only standard-library imports (`json`, `os`, `urllib.error`, `urllib.request`).
- With no config file, `python3 -m offload doctor 2>&1 | grep -i "discord webhook"` prints one line (the default notifier is still Discord).
- No behaviour change for an owner whose config sets only `webhook_file`.
