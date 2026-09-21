"""A job's checkpoint, persisted in `<job>/progress.json`, so that a parked or interrupted job resumes where it stopped.

`phase` is the phase to run next. In the `steps` phase, `step` is the first step that is not finished.
`pending` names a Claude session that a provider limit cut short: {"purpose": ..., "session": ...}.
"""
from offload.files import read_json, write_json

PLAN = "plan"
STEPS = "steps"
REVIEW = "review"
COMMIT = "commit"
GATE = "gate"
PUSH = "push"
PHASES = (PLAN, STEPS, REVIEW, COMMIT, GATE, PUSH)


def load(job):
    """The checkpoint record. A job with no checkpoint is at the plan."""
    try:
        return read_json(job.path("progress.json"))
    except FileNotFoundError:
        return {"phase": PLAN}


def save(job, **fields):
    """Merge fields into the checkpoint and return it."""
    record = load(job)
    record.update(fields)
    write_json(job.path("progress.json"), record)
    return record


def still_to_run(record, phase):
    """True when `phase` is not finished yet: the checkpoint is at `phase` or at an earlier one."""
    return PHASES.index(record.get("phase", PLAN)) <= PHASES.index(phase)


def pending_session(job, purpose):
    """The session id of a Claude call for `purpose` that a limit cut short, or None."""
    pending = load(job).get("pending") or {}
    return pending.get("session") if pending.get("purpose") == purpose else None
