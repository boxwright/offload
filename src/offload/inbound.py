"""Answers from the Discord channel: read the owner's replies back with a bot token.

`make_inbox(config)` builds a `DiscordInbox` when the bot token, channel, and owner id are all set, else
`None` (and nothing changes). Every method returns a value and never raises, so a flaky network can never
stop the daemon's loop.
"""
import json
import os
import urllib.error
import urllib.request

DISCORD_EPOCH_MS = 1420070400000


def snowflake_after(epoch_seconds):
    """The Discord snowflake for that moment; a moment before the Discord epoch returns 0."""
    ms = int(epoch_seconds * 1000) - DISCORD_EPOCH_MS
    if ms < 0:
        return 0
    return ms << 22


class DiscordInbox:
    """The owner's replies in one channel, read with a bot token. Nothing here raises."""

    def __init__(self, token, channel_id, owner_id, api="https://discord.com/api/v10"):
        self.token = token
        self.channel_id = channel_id
        self.owner_id = owner_id
        self.api = api

    def _headers(self):
        return {"Authorization": f"Bot {self.token}", "User-Agent": "offload/0.1"}

    def messages_after(self, after_id):
        """The owner's non-bot messages after `after_id`, oldest first. Never raises; [] on any failure."""
        url = f"{self.api}/channels/{self.channel_id}/messages?after={after_id}&limit=50"
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        messages = []
        for message in data:
            if not isinstance(message, dict):
                continue
            author = message.get("author")
            if not isinstance(author, dict) or author.get("id") != self.owner_id or author.get("bot"):
                continue
            messages.append({"id": str(message.get("id", "")), "text": message.get("content", ""),
                             "ts": message.get("timestamp", "")})
        messages.reverse()   # Discord returns newest first; the daemon wants oldest first
        return messages

    def acknowledge(self, message_id):
        """React to the message with a check mark. True on a 2xx, False otherwise. Never raises."""
        url = f"{self.api}/channels/{self.channel_id}/messages/{message_id}/reactions/%E2%9C%85/@me"
        request = urllib.request.Request(url, data=b"", headers=self._headers(), method="PUT")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False


def make_inbox(config):
    """A DiscordInbox when the bot token, channel, and owner id are all set; else None."""
    if config.notifier != "discord" or not config.discord_channel_id or not config.discord_owner_id:
        return None
    if not os.path.isfile(config.discord_bot_token_file):
        return None
    try:
        with open(config.discord_bot_token_file) as f:
            token = f.readline().strip()
    except OSError:
        return None
    if not token:
        return None
    return DiscordInbox(token, config.discord_channel_id, config.discord_owner_id)


def is_configured(config):
    """True when make_inbox(config) would return an inbox, without reading the token."""
    if config.notifier != "discord" or not config.discord_channel_id or not config.discord_owner_id:
        return False
    return os.path.isfile(config.discord_bot_token_file)
