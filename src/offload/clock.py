"""Wall-clock timestamps, in the one format the engine writes to its logs."""
import time

TS_FMT = "%Y-%m-%d %H:%M:%S"


def now() -> str:
    """The current local time as a sortable string."""
    return time.strftime(TS_FMT)
