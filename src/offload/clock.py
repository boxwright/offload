"""Wall-clock timestamps, in the one format the engine writes to its logs, and the wake times of parked jobs."""
import datetime as dt
import time

TS_FMT = "%Y-%m-%d %H:%M:%S"


def now() -> str:
    """The current local time as a sortable string."""
    return time.strftime(TS_FMT)


def iso_after(seconds) -> str:
    """The local time `seconds` from now, as an ISO string with its zone."""
    return (dt.datetime.now().astimezone() + dt.timedelta(seconds=seconds)).isoformat()


def is_past(iso_time) -> bool:
    """True when the ISO time is now or earlier. A missing or unreadable time counts as past: nothing waits forever."""
    try:
        moment = dt.datetime.fromisoformat(iso_time)
    except (TypeError, ValueError):
        return True
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment <= dt.datetime.now().astimezone()
