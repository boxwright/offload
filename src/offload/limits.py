"""Provider rate limits: recognise the message and work out when the window reopens. Pure logic."""
import contextlib
import datetime as dt
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LIMIT_RE = re.compile(r"hit your (session|weekly|usage|monthly spend) limit", re.I)
MAX_LIMIT_WAITS = 6
WAIT_CHUNK_S = 1800

_RELATIVE_RE = re.compile(r"resets? in (\d+)\s*(minute|min|hour|hr)s?", re.I)
_CLOCK_RE = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)(?:\s*\(([^)]+)\))?", re.I)


def limit_kind(text):
    """`session`, `weekly`, `usage` or `monthly spend`, or None when the text is not a limit message."""
    match = LIMIT_RE.search(text)
    return match.group(1) if match else None


def parse_reset(text, now=None):
    """When the limit lifts, read from the CLI's message, or None.

    Shapes seen: "You've hit your session limit · resets 7pm (America/New_York)",
    "resets 3:30pm", "resets in 45 minutes".
    """
    now = now or dt.datetime.now().astimezone()
    relative = _RELATIVE_RE.search(text)
    if relative:
        amount = int(relative.group(1))
        minutes = amount if relative.group(2).lower().startswith("min") else amount * 60
        return now + dt.timedelta(minutes=minutes)
    clock = _CLOCK_RE.search(text)
    if not clock:
        return None
    hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
    meridiem, zone_name = clock.group(3).lower(), clock.group(4)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    local_now = now
    if zone_name:
        with contextlib.suppress(ZoneInfoNotFoundError, ValueError):
            local_now = now.astimezone(ZoneInfo(zone_name))
    reset = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if reset <= local_now:
        reset += dt.timedelta(days=1)
    return reset


def simulated_limit_message(minutes, now=None):
    """The message a session limit would produce if the window reopened `minutes` from now (local time)."""
    now = now or dt.datetime.now().astimezone()
    reset = (now + dt.timedelta(minutes=minutes)).strftime("%I:%M%p").lstrip("0").lower()
    return f"You've hit your session limit · resets {reset}"
