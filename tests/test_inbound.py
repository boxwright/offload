"""Answers from Discord: the inbox reads the owner's replies back, and the daemon's poll writes them in.

Every test runs against a threaded http.server.HTTPServer on 127.0.0.1:0, shaped like test_notifiers.py.
"""
import dataclasses
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import make_job_dir

from offload import config, daemon, files, inbound, notify, status
from offload.jobs import Job

OWNER = "1000000000000000001"
OTHER = "2000000000000000002"


def _message(mid, text, author=OWNER, bot=False, ts="2026-01-01T00:00:00.000000+00:00"):
    return {"id": mid, "content": text, "timestamp": ts,
            "author": {"id": author, "bot": bot}}


class _DiscordHandler(BaseHTTPRequestHandler):
    """Records each request and answers from the server's `responses` map, keyed by (method, path)."""

    def _respond(self):
        self.server.requests.append((self.command, self.path, dict(self.headers),
                                     self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0)))
        body = self.server.responses.get((self.command, urlsplit(self.path).path))
        status_code = 200
        if body is None:
            body, status_code = b"[]", 200
        elif isinstance(body, int):
            status_code, body = body, b""
        elif not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._respond()

    def do_PUT(self):
        self._respond()

    def log_message(self, *args):
        pass


@pytest.fixture
def discord_server():
    """A daemon-thread Discord-shaped server on 127.0.0.1:0. Records (method, path, headers, body) per request."""
    server = HTTPServer(("127.0.0.1", 0), _DiscordHandler)
    server.requests = []
    server.responses = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _inbox(server, **kwargs):
    return inbound.DiscordInbox("secret-token", "999999999999999999", OWNER,
                                 api=f"http://127.0.0.1:{server.server_address[1]}", **kwargs)


@pytest.fixture(autouse=True)
def _reset_poll_state():
    """The daemon's poll globals are process-wide; each test starts from a clean slate."""
    daemon._last_poll = 0.0
    daemon._last_message_id = 0
    yield


@pytest.fixture
def quiet(settings, monkeypatch):
    """No webhook post, and the ledger and the budget file live in tmp_path."""
    monkeypatch.setattr(notify, "post", lambda text: (False, "test"))
    daemon._finished.clear()


# --- snowflakes -----------------------------------------------------------

def test_snowflake_after_the_discord_epoch_is_shifted_ms():
    # 1 second after the epoch: 1000 ms << 22
    assert inbound.snowflake_after(inbound.DISCORD_EPOCH_MS / 1000 + 1) == (1000 << 22)


def test_snowflake_before_the_discord_epoch_is_zero():
    assert inbound.snowflake_after(0) == 0
    assert inbound.snowflake_after(inbound.DISCORD_EPOCH_MS / 1000 - 100) == 0


def test_snowflake_grows_with_time():
    earlier = inbound.snowflake_after(1_700_000_000)
    later = inbound.snowflake_after(1_700_000_060)
    assert later > earlier
    assert (later - earlier) == (60 * 1000 << 22)


# --- messages_after -------------------------------------------------------

def test_messages_after_sends_the_bot_token_and_asks_for_the_channel(discord_server):
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("1", "yes")]
    inbox = _inbox(discord_server)
    assert inbox.messages_after(0) == [{"id": "1", "text": "yes", "ts": "2026-01-01T00:00:00.000000+00:00"}]
    method, path, headers, _ = discord_server.requests[0]
    assert method == "GET"
    assert headers["Authorization"] == "Bot secret-token"
    assert headers["User-Agent"] == "offload/0.1"
    query = parse_qs(urlsplit(path).query)
    assert urlsplit(path).path == "/channels/999999999999999999/messages"
    assert query == {"after": ["0"], "limit": ["50"]}


def test_messages_after_keeps_only_the_owner_and_drops_bots(discord_server):
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("5", "a bot says hi", bot=True),
        _message("4", "someone else", author=OTHER),
        _message("3", "owner newest"),
        _message("2", "owner oldest"),
    ]
    inbox = _inbox(discord_server)
    assert [m["id"] for m in inbox.messages_after(0)] == ["2", "3"]
    assert [m["text"] for m in inbox.messages_after(0)] == ["owner oldest", "owner newest"]


def test_messages_after_drops_non_dict_entries_and_missing_author(discord_server):
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        "not a dict",
        {"id": "9", "content": "no author"},
        {"id": "8", "content": "yes", "timestamp": "2026-01-01T00:00:00.000000+00:00", "author": {"id": OWNER}},
    ]
    inbox = _inbox(discord_server)
    assert inbox.messages_after(0) == [{"id": "8", "text": "yes", "ts": "2026-01-01T00:00:00.000000+00:00"}]


def test_messages_after_returns_empty_on_a_bad_status(discord_server):
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = 403
    assert _inbox(discord_server).messages_after(0) == []


def test_messages_after_returns_empty_on_a_non_list_body(discord_server):
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = {"error": "nope"}
    assert _inbox(discord_server).messages_after(0) == []


def test_messages_after_returns_empty_when_the_server_is_down(discord_server):
    port = discord_server.server_address[1]
    discord_server.shutdown()
    discord_server.server_close()
    inbox = inbound.DiscordInbox("t", "c", OWNER, api=f"http://127.0.0.1:{port}")
    assert inbox.messages_after(0) == []


# --- acknowledge ----------------------------------------------------------

def test_acknowledge_reacts_with_a_check_mark(discord_server):
    discord_server.responses[("PUT", "/channels/999999999999999999/messages/42/reactions/%E2%9C%85/@me")] = {}
    assert _inbox(discord_server).acknowledge("42") is True
    method, path, headers, _ = discord_server.requests[0]
    assert method == "PUT"
    assert path == "/channels/999999999999999999/messages/42/reactions/%E2%9C%85/@me"
    assert headers["Authorization"] == "Bot secret-token"


def test_acknowledge_is_false_on_a_bad_status(discord_server):
    discord_server.responses[("PUT", "/channels/999999999999999999/messages/42/reactions/%E2%9C%85/@me")] = 404
    assert _inbox(discord_server).acknowledge("42") is False


def test_acknowledge_is_false_when_the_server_is_down(discord_server):
    port = discord_server.server_address[1]
    discord_server.shutdown()
    discord_server.server_close()
    assert inbound.DiscordInbox("t", "c", OWNER, api=f"http://127.0.0.1:{port}").acknowledge("42") is False


# --- make_inbox / is_configured ------------------------------------------

def _discord_config(settings, **overrides):
    values = {"notifier": "discord", "discord_channel_id": "999999999999999999", "discord_owner_id": OWNER}
    values.update(overrides)
    return dataclasses.replace(settings, **values)


def test_make_inbox_builds_an_inbox_when_everything_is_set(settings, tmp_path):
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    inbox = inbound.make_inbox(_discord_config(settings))
    assert isinstance(inbox, inbound.DiscordInbox)
    assert inbox.token == "the-token"
    assert inbox.channel_id == "999999999999999999"
    assert inbox.owner_id == OWNER


def test_make_inbox_is_none_without_a_channel_id(settings, tmp_path):
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    assert inbound.make_inbox(_discord_config(settings, discord_channel_id="")) is None


def test_make_inbox_is_none_without_an_owner_id(settings, tmp_path):
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    assert inbound.make_inbox(_discord_config(settings, discord_owner_id="")) is None


def test_make_inbox_is_none_when_the_notifier_is_not_discord(settings, tmp_path):
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    assert inbound.make_inbox(_discord_config(settings, notifier="ntfy")) is None


def test_make_inbox_is_none_without_the_token_file(settings, tmp_path):
    assert inbound.make_inbox(_discord_config(settings)) is None


def test_make_inbox_is_none_when_the_token_file_is_blank(settings, tmp_path):
    (tmp_path / "discord-bot-token").write_text("   \n")
    assert inbound.make_inbox(_discord_config(settings)) is None


def test_is_configured_matches_make_inbox(settings, tmp_path):
    assert inbound.is_configured(_discord_config(settings)) is False   # no token file yet
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    assert inbound.is_configured(_discord_config(settings)) is True
    assert inbound.is_configured(_discord_config(settings, notifier="ntfy")) is False


# --- _collect_answers: one gate ------------------------------------------

def test_collect_answers_writes_the_whole_text_as_the_answer(settings, tmp_path, discord_server, quiet):
    deadline = 1_700_000_000
    job_dir = make_job_dir(tmp_path, "a-gate", {"id": "a-gate"})
    status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=deadline)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("11", "yes, go ahead")]
    inbox = _inbox(discord_server)

    assert daemon._collect_answers(str(tmp_path), inbox) == 1
    assert (tmp_path / "a-gate" / "answer.txt").read_text().strip() == "yes, go ahead"
    # the poll asks for messages after the snowflake floor: deadline - gate_wait_s
    query = parse_qs(urlsplit(discord_server.requests[0][1]).query)
    assert query["after"] == [str(inbound.snowflake_after(deadline - settings.gate_wait_s))]
    # the answer is acknowledged with a check mark
    assert ("PUT", "/channels/999999999999999999/messages/11/reactions/%E2%9C%85/@me") in [
        (m, p) for m, p, _, _ in discord_server.requests]
    events = _events(job_dir)
    assert any(e["kind"] == "answer_from_chat" and e["message_id"] == "11" and e["text"] == "yes, go ahead"
               for e in events)


def _events(job_dir):
    return list(files.read_jsonl(os.path.join(job_dir, "events.jsonl")))


# --- _collect_answers: two gates ------------------------------------------

def test_collect_answers_routes_each_reply_by_job_id(settings, tmp_path, discord_server, quiet):
    for name in ("a-gate", "b-gate"):
        job_dir = make_job_dir(tmp_path, name, {"id": name})
        status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("21", "a-gate no"),
        _message("22", "b-gate yes"),
    ]
    inbox = _inbox(discord_server)

    assert daemon._collect_answers(str(tmp_path), inbox) == 2
    assert (tmp_path / "a-gate" / "answer.txt").read_text().strip() == "no"
    assert (tmp_path / "b-gate" / "answer.txt").read_text().strip() == "yes"


def test_collect_answers_matches_an_unambiguous_job_id_prefix(settings, tmp_path, discord_server, quiet):
    for name in ("a-gate", "b-gate"):
        job_dir = make_job_dir(tmp_path, name, {"id": name})
        status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("31", "a yes"),
    ]
    inbox = _inbox(discord_server)

    assert daemon._collect_answers(str(tmp_path), inbox) == 1
    assert (tmp_path / "a-gate" / "answer.txt").read_text().strip() == "yes"
    assert not (tmp_path / "b-gate" / "answer.txt").exists()


# --- _collect_answers: the ambiguous / unmatched message ------------------

def test_collect_answers_ignores_a_reply_without_a_job_id(settings, tmp_path, discord_server, quiet):
    for name in ("a-gate", "b-gate"):
        job_dir = make_job_dir(tmp_path, name, {"id": name})
        status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("41", "yes"),
    ]
    inbox = _inbox(discord_server)

    assert daemon._collect_answers(str(tmp_path), inbox) == 0
    assert not (tmp_path / "a-gate" / "answer.txt").exists()
    assert not (tmp_path / "b-gate" / "answer.txt").exists()
    # the miss is logged on the oldest open gate
    events = _events(tmp_path / "a-gate")
    assert any(e["kind"] == "answer_ignored" and e["message_id"] == "41" and e["reason"] == "no job id"
               for e in events)
    assert not any(e["kind"] == "answer_ignored" for e in _events(tmp_path / "b-gate"))


def test_collect_answers_ignores_a_reply_matching_two_gates(settings, tmp_path, discord_server, quiet):
    for name in ("a-gate", "a2-gate"):
        job_dir = make_job_dir(tmp_path, name, {"id": name})
        status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [
        _message("51", "a yes"),
    ]
    inbox = _inbox(discord_server)

    assert daemon._collect_answers(str(tmp_path), inbox) == 0
    assert not (tmp_path / "a-gate" / "answer.txt").exists()
    assert not (tmp_path / "a2-gate" / "answer.txt").exists()
    events = _events(tmp_path / "a-gate")
    assert any(e["kind"] == "answer_ignored" and e["message_id"] == "51" and e["reason"] == "ambiguous"
               for e in events)


# --- _collect_answers: the 30 s throttle ----------------------------------

def test_collect_answers_polls_at_most_once_per_interval(settings, tmp_path, discord_server, quiet):
    job_dir = make_job_dir(tmp_path, "a-gate", {"id": "a-gate"})
    status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    discord_server.responses[("GET", "/channels/999999999999999999/messages")] = [_message("61", "yes")]
    inbox = _inbox(discord_server)

    daemon._last_poll = time.time()     # a poll just happened
    assert daemon._collect_answers(str(tmp_path), inbox) == 0
    assert discord_server.requests == []   # throttled: nothing was read
    assert not (tmp_path / "a-gate" / "answer.txt").exists()


def test_collect_answers_does_nothing_without_an_inbox_or_a_gate(settings, tmp_path, discord_server, quiet):
    job_dir = make_job_dir(tmp_path, "a-gate", {"id": "a-gate"})
    status.set_status(job_dir, status.WAITING_OWNER, gate="publish", deadline=1_700_000_000)
    assert daemon._collect_answers(str(tmp_path), None) == 0
    assert discord_server.requests == []
    status.set_status(job_dir, status.DONE)
    assert daemon._collect_answers(str(tmp_path), _inbox(discord_server)) == 0
    assert discord_server.requests == []


# --- ask_owner's two sentences --------------------------------------------

def test_ask_owner_says_reply_here_when_the_inbox_is_configured(settings, tmp_path, monkeypatch):
    (tmp_path / "discord-bot-token").write_text("the-token\n")
    config.set_config(dataclasses.replace(settings, notifier="discord",
                                          discord_channel_id="999999999999999999", discord_owner_id=OWNER))
    posted = []
    monkeypatch.setattr(notify, "post", lambda text: posted.append(text) or (True, 200))
    job = Job(make_job_dir(tmp_path, "a-gate", {"id": "a-gate"}))
    with pytest.raises(status.Parked):
        notify.ask_owner(job, "publish", "Push to main?")
    assert posted and posted[-1].endswith(
        "Reply here with yes or no. Start with the job id when more than one job is waiting.")


def test_ask_owner_says_reply_on_the_engine_host_when_not_configured(settings, tmp_path, monkeypatch):
    posted = []
    monkeypatch.setattr(notify, "post", lambda text: posted.append(text) or (True, 200))
    job = Job(make_job_dir(tmp_path, "a-gate", {"id": "a-gate"}))
    with pytest.raises(status.Parked):
        notify.ask_owner(job, "publish", "Push to main?")
    assert posted and posted[-1].endswith(
        f"Reply on the engine host: `offload answer {job.dir} \"yes\"` (or no, or your own text)")


def test_a_message_after_the_last_gate_is_answered_does_not_crash_the_poll(settings, tmp_path, monkeypatch):
    """Live on 2026-09-26: a second message in the same batch, after the only gate was consumed, raised IndexError."""
    from offload import daemon, status
    gate = make_job_dir(tmp_path / "jobs", "only", {"id": "only", "repo": "/r.git"})
    status.set_status(gate, status.WAITING_OWNER, gate="confirm", deadline=time.time() + 60)

    class Inbox:
        acked = []

        def messages_after(self, after):
            return [{"id": "1", "text": "yes", "ts": ""}, {"id": "2", "text": "thanks", "ts": ""}]

        def acknowledge(self, message_id):
            self.acked.append(message_id)
            return True
    daemon._last_poll = 0.0
    daemon._last_message_id = 0
    assert daemon._collect_answers(tmp_path / "jobs", Inbox()) == 1
    assert Inbox.acked == ["1"]
    assert daemon._last_message_id == 1
