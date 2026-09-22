"""Shared fixtures. No test touches the network, Docker, or the real home directory."""
import dataclasses
import os
import types

import pytest

from offload import budget, config, jobs, limits, results, status


@pytest.fixture
def settings(tmp_path):
    """A Config whose files all live in tmp_path, installed for the length of the test."""
    test_config = dataclasses.replace(
        config.Config(), jobs_root=str(tmp_path / "jobs"), ledger=str(tmp_path / "ledger.jsonl"),
        budget_file=str(tmp_path / "budget.yaml"), repos_file=str(tmp_path / "repos.yaml"),
        token_file=str(tmp_path / "claude-token"), webhook_file=str(tmp_path / "discord-webhook"),
        pause_file=str(tmp_path / "PAUSE"))
    previous = config.set_config(test_config)
    yield test_config
    config.set_config(previous)


@pytest.fixture(scope="session")
def api():
    """The functions under test, gathered from their modules."""
    return types.SimpleNamespace(
        parse_reset=limits.parse_reset,
        week_start=budget.week_start,
        ledger_add=budget.ledger_add,
        spent_since=budget.spent_since,
        pace_status=budget.pace_status,
        job_cost=budget.job_cost,
        job_status=status.job_status,
        set_status=status.set_status,
        is_stuck=results.is_stuck,
        Job=jobs.Job,
    )


@pytest.fixture
def api_isolated(api, settings):
    """`api`, with the ledger and the budget file redirected into tmp_path."""
    return api


def make_job_dir(root, name="job-001", meta=None, body="## Goal\nDo the thing\n"):
    """Create a job directory with a job.md under root. Leave `repo` out of meta for an inbox job."""
    job_dir = os.path.join(os.fspath(root), name)
    os.makedirs(job_dir, exist_ok=True)
    meta = {"id": name} if meta is None else meta
    front_matter = "\n".join(f"{key}: {value}" for key, value in meta.items())
    with open(os.path.join(job_dir, "job.md"), "w") as f:
        f.write(f"---\n{front_matter}\n---\n{body}")
    return job_dir


@pytest.fixture
def job_factory(tmp_path):
    """`make_job_dir` bound to this test's tmp_path."""
    def factory(name="job-001", meta=None, body="## Goal\nDo the thing\n"):
        return make_job_dir(tmp_path, name, meta, body)
    return factory
