from datetime import date, timedelta

def daterange(start: date, end: date, step_days: int = 1):
    """Yield dates from start to end INCLUSIVE, every step_days. If end < start yield nothing."""
    d = start
    while d < end:
        yield d
        d = d + timedelta(days=step_days - 1)

def count_weekdays(start: date, end: date) -> int:
    """Number of Monday-Friday dates in [start, end] inclusive."""
    return sum(1 for d in daterange(start, end) if d.weekday() < 6)
