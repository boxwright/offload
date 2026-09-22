"""The budget: a ledger of Claude calls, and a pacer that spreads a weekly allowance evenly.

Costs are in USD at API list prices, as Claude Code reports them per call. On a subscription that
figure is a yardstick for pacing, not a bill.

The ledger and budget file come from the config, read at call time, so tests can point them at a temporary directory.
"""
import datetime as dt
import glob
import itertools
import os
import time
from collections import defaultdict
from typing import NamedTuple

from offload import status
from offload.clock import iso_after, now
from offload.config import get_config
from offload.files import append_jsonl, read_jsonl

WEEK_S = 7 * 86400
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_budget_cache = {}


class Pace(NamedTuple):
    allowed: bool
    spent: float        # this week, USD list-equivalent
    pace_now: float     # what an even spend would have reached by now
    allowance: float    # the engine's share of the week
    wait_s: int         # seconds until a call is allowed again


def load_budget():
    """The parsed budget file, cached until the file changes. A missing file means defaults."""
    path = get_config().budget_file
    try:
        stat = os.stat(path)
    except OSError:
        return {}
    key = (path, stat.st_mtime_ns, stat.st_size)
    if _budget_cache.get("key") != key:
        import yaml
        with open(path) as f:
            try:
                data = yaml.safe_load(f) or {}
            except yaml.YAMLError as exc:
                raise ValueError(f"{path} is not valid YAML: {exc}") from exc
        _budget_cache.update(key=key, data=data)
    return _budget_cache["data"]


def _parse_week_resets(spec):
    """`"Tue 22:00"` -> (1, 22, 0). The weekday defaults to Tuesday and the time to midnight."""
    parts = str(spec).split()
    weekday = _WEEKDAYS.get(parts[0][:3].lower(), 1) if parts else 1
    hour, minute = 0, 0
    if len(parts) > 1:
        clock = parts[1].split(":")
        hour = int(clock[0])
        minute = int(clock[1]) if len(clock) > 1 else 0
    return weekday, hour, minute


def week_start(budget, now=None):
    """The most recent moment the subscription's weekly window reset."""
    now = now or dt.datetime.now().astimezone()
    weekday, hour, minute = _parse_week_resets(budget.get("claude", {}).get("week_resets", "Tue 22:00"))
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    start -= dt.timedelta(days=(start.weekday() - weekday) % 7)
    if start > now:
        start -= dt.timedelta(days=7)
    return start


def ledger_add(job, model, purpose, usd, cache_read, output_tokens):
    path = get_config().ledger
    os.makedirs(os.path.dirname(path), exist_ok=True)
    append_jsonl(path, {
        "t": now(), "ts": time.time(), "job": job.id, "model": model, "purpose": purpose,
        "usd": round(usd or 0, 5), "cache_read": cache_read, "output_tokens": output_tokens,
    })


def _ledger_rows():
    """Every ledger record. A line damaged by a crash mid-write is skipped rather than stopping the pacer."""
    return read_jsonl(get_config().ledger, strict=False)


def _archive_rows():
    """Every record in the monthly `ledger-YYYY-MM.jsonl` archives beside the ledger. The pacer never reads these."""
    stem, ext = os.path.splitext(get_config().ledger)
    for path in sorted(glob.glob(f"{stem}-*{ext}")):
        yield from read_jsonl(path, strict=False)


def spent_since(timestamp):
    return sum(row.get("usd", 0) for row in _ledger_rows() if row.get("ts", 0) >= timestamp)


def job_costs():
    """One pass over the archives and the ledger: {job id: (total, {model: usd})}."""
    totals = defaultdict(float)
    per_model = defaultdict(lambda: defaultdict(float))
    for row in itertools.chain(_archive_rows(), _ledger_rows()):
        usd = row.get("usd", 0)
        totals[row.get("job")] += usd
        per_model[row.get("job")][row.get("model")] += usd
    return {job_id: (totals[job_id], dict(per_model[job_id])) for job_id in totals}


def job_cost(job_id):
    return job_costs().get(job_id, (0.0, {}))


def pace_status(budget, now=None):
    now = now or dt.datetime.now().astimezone()
    claude = budget.get("claude", {})
    allowance = float(claude.get("weekly_usd_equivalent", 150)) * float(claude.get("allowance_percent", 60)) / 100.0
    start = week_start(budget, now)
    elapsed = (now - start).total_seconds()
    spent = spent_since(start.timestamp())
    if str(claude.get("pace", "even")) != "even":
        return Pace(True, spent, allowance, allowance, 0)
    pace_now = allowance * elapsed / WEEK_S
    slack = 1 + float(claude.get("slack_percent", 15)) / 100.0
    if spent >= allowance:
        return Pace(False, spent, pace_now, allowance, int(WEEK_S - elapsed) + 60)
    if spent <= pace_now * slack:
        return Pace(True, spent, pace_now, allowance, 0)
    # Seconds until the even pace, with its slack, catches up with what was spent.
    catch_up = spent / slack / allowance * WEEK_S - elapsed
    return Pace(False, spent, pace_now, allowance, int(max(60, catch_up)))


def budget_wait(job, purpose):
    """Return when the pacer allows a Claude call. Otherwise park the job until the pacer's next opening."""
    pace = pace_status(load_budget())
    if pace.allowed:
        return
    job.event("budget_wait", purpose=purpose, spent_usd=round(pace.spent, 3),
              pace_usd=round(pace.pace_now, 3), allowance_usd=pace.allowance, wait_s=pace.wait_s)
    raise status.Parked(status.WAITING_BUDGET, until=iso_after(pace.wait_s), wait_s=pace.wait_s)


def model_for(purpose):
    """Which Claude model a call uses: `plan`, `rescue …` and everything else (`review`)."""
    models = load_budget().get("claude", {}).get("models", {})
    if purpose.startswith("rescue"):
        key = "rescue"
    elif purpose == "plan":
        key = "plan"
    else:
        key = "review"
    return str(models.get(key, "sonnet"))


def cost_table():
    pace = pace_status(load_budget())
    last_day = spent_since(time.time() - 86400)
    state = "on pace" if pace.allowed else f"waiting {pace.wait_s // 60} min"
    print(f"week: ${pace.spent:.2f} of ${pace.allowance:.0f} allowance "
          f"(even pace ${pace.pace_now:.2f}) → {state} | last 24 h: ${last_day:.2f}")
    for job_id, (_, per_model) in sorted(job_costs().items()):
        for model, usd in sorted(per_model.items()):
            print(f"  {job_id:<18} {model:<8} ${usd:.2f}")
