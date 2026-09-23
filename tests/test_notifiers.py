"""The notifiers: Discord and ntfy, each against a local HTTP server that records what it receives."""
import dataclasses
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from offload import config, notifiers, notify


class _RecordingHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.server.requests.append((self.path, dict(self.headers), self.rfile.read(length)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    """A daemon-thread HTTP server on 127.0.0.1:0. Records (path, headers, body) per request and answers 200."""
    server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_discord_posts_the_message_as_json(http_server, tmp_path):
    webhook = tmp_path / "discord-webhook"
    webhook.write_text(f"http://127.0.0.1:{http_server.server_address[1]}/webhooks/42\n")
    ok, detail = notifiers.DiscordNotifier(str(webhook)).post("hello world")
    assert ok is True and detail == 200
    path, headers, body = http_server.requests[0]
    assert path == "/webhooks/42"
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"content": "hello world", "username": "offload"}


def test_discord_truncates_the_message_to_1900_characters(http_server, tmp_path):
    webhook = tmp_path / "discord-webhook"
    webhook.write_text(f"http://127.0.0.1:{http_server.server_address[1]}/w\n")
    ok, _ = notifiers.DiscordNotifier(str(webhook)).post("x" * 2500)
    assert ok is True
    assert json.loads(http_server.requests[0][2])["content"] == "x" * 1900


def test_discord_without_a_webhook_file_does_not_raise(tmp_path):
    ok, detail = notifiers.DiscordNotifier(str(tmp_path / "missing-webhook")).post("hello")
    assert ok is False and detail == "no webhook file"


def test_ntfy_posts_plain_text_with_a_title(http_server):
    ok, detail = notifiers.NtfyNotifier(f"http://127.0.0.1:{http_server.server_address[1]}/topic").post("plain hello")
    assert ok is True and detail == 200
    path, headers, body = http_server.requests[0]
    assert path == "/topic"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["Title"] == "offload"
    assert body == b"plain hello"


def test_ntfy_sends_a_bearer_token_from_the_token_file(http_server, tmp_path):
    token_file = tmp_path / "ntfy-token"
    token_file.write_text("tok123\n")
    ok, _ = notifiers.NtfyNotifier(f"http://127.0.0.1:{http_server.server_address[1]}/topic",
                                   str(token_file)).post("hi")
    assert ok is True
    _, headers, _ = http_server.requests[0]
    assert headers["Authorization"] == "Bearer tok123"


def test_ntfy_against_a_closed_port_fails_cleanly(http_server):
    # The server is shut down, so nothing is listening on its port any more.
    http_server.shutdown()
    http_server.server_close()
    ok, detail = notifiers.NtfyNotifier(f"http://127.0.0.1:{http_server.server_address[1]}/topic").post("hi")
    assert ok is False
    assert detail


def test_make_notifier_dispatches_on_the_config():
    cfg = config.Config(notifier="discord", webhook_file="/w", ntfy_url="http://u", ntfy_token_file="/t")
    assert isinstance(notifiers.make_notifier(cfg), notifiers.DiscordNotifier)
    assert notifiers.make_notifier(cfg).webhook_file == "/w"
    assert isinstance(notifiers.make_notifier(dataclasses.replace(cfg, notifier="ntfy")), notifiers.NtfyNotifier)
    assert isinstance(notifiers.make_notifier(dataclasses.replace(cfg, notifier="none")), notifiers.Notifier)


def test_make_notifier_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="slack"):
        notifiers.make_notifier(config.Config(notifier="slack"))


def test_notify_post_routes_through_the_installed_config(http_server, tmp_path):
    webhook = tmp_path / "discord-webhook"
    webhook.write_text(f"http://127.0.0.1:{http_server.server_address[1]}/n\n")
    cfg = dataclasses.replace(config.Config(), notifier="discord", webhook_file=str(webhook))
    previous = config.set_config(cfg)
    try:
        ok, detail = notify.post("routed")
    finally:
        config.set_config(previous)
    assert ok is True and detail == 200
    assert json.loads(http_server.requests[0][2]) == {"content": "routed", "username": "offload"}
