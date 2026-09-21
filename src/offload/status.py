"""A job's lifecycle status, persisted in `<job>/status.json`."""
import json
import os

from offload.clock import now
from offload.files import read_json, write_json

INBOX = "inbox"
READY = "ready"
RUNNING = "running"
WAITING_OWNER = "waiting_owner"
WAITING_LIMIT = "waiting_limit"
WAITING_BUDGET = "waiting_budget"
DONE = "done"
FAILED = "failed"

# A parked job holds no worker. The daemon runs other jobs and comes back when the wake condition is true.
WAITING = {WAITING_OWNER, WAITING_LIMIT, WAITING_BUDGET}


class Parked(Exception):
    """Raised at a long wait. The daemon records `status` with the `wake` fields and runs the next job.

    Wake fields: `deadline` (epoch seconds) and `gate` for an owner gate, `until` (ISO time) for a limit or the budget.
    """

    def __init__(self, status, **wake):
        super().__init__(status)
        self.status = status
        self.wake = wake


def job_status(job_dir):
    """The job's status record. A job with no status file is `ready` if it has a job.md, else `inbox`."""
    path = os.path.join(job_dir, "status.json")
    try:
        return read_json(path)
    except FileNotFoundError:
        has_job_file = os.path.exists(os.path.join(job_dir, "job.md"))
        return {"status": READY if has_job_file else INBOX}
    except json.JSONDecodeError:
        return {"status": FAILED, "reason": "status.json is not valid JSON"}


def set_status(job_dir, status, **fields):
    """Merge `status` and any extra fields into the job's status record, and return it."""
    record = job_status(job_dir)
    record.update({"status": status, "updated": now(), **fields})
    write_json(os.path.join(job_dir, "status.json"), record)
    return record
