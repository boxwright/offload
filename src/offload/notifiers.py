"""Where offload posts its messages: the Discord webhook, an ntfy server, or nowhere.

`make_notifier(config)` builds the notifier named by `config.notifier` — "discord", "ntfy", or "none".
Every notifier's `post(text)` returns `(ok, detail)` and never raises.
"""
import json
import urllib.error
import urllib.request


class Notifier:
    """The base: a notifier that posts nowhere."""

    def post(self, text):
        return False, "no notifier configured"


class DiscordNotifier(Notifier):
    """The Discord webhook: the URL lives in a file that only the owner can read."""

    def __init__(self, webhook_file):
        self.webhook_file = webhook_file

    def post(self, text):
        """Post one message. Returns (ok, detail) and never raises."""
        try:
            with open(self.webhook_file) as f:
                url = f.read().strip()
        except FileNotFoundError:
            return False, "no webhook file"
        body = json.dumps({"content": text[:1900], "username": "offload"}).encode()
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json", "User-Agent": "offload/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return True, response.status
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, str(exc)[:120]


class NtfyNotifier(Notifier):
    """An ntfy server: the first 4000 characters as plain text, with an optional bearer token."""

    def __init__(self, url, token_file=""):
        self.url = url
        self.token_file = token_file

    def post(self, text):
        """Post the message as plain text. Returns (ok, detail) and never raises."""
        headers = {"Content-Type": "text/plain; charset=utf-8", "Title": "offload"}
        if self.token_file:
            try:
                with open(self.token_file) as f:
                    token = f.readline().strip()
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            except FileNotFoundError:
                pass
        request = urllib.request.Request(self.url, data=text[:4000].encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return True, response.status
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, str(exc)[:120]


def make_notifier(config):
    """The notifier named by `config.notifier`: discord, ntfy, or none."""
    if config.notifier == "discord":
        return DiscordNotifier(config.webhook_file)
    if config.notifier == "ntfy":
        return NtfyNotifier(config.ntfy_url, config.ntfy_token_file)
    if config.notifier == "none":
        return Notifier()
    raise ValueError(f"unknown notifier {config.notifier!r}: allowed are discord, ntfy, none")
