"""Tests for `resolve_job_id`: turning a job id or a unique prefix into the one job id it names.

An exact match wins even when it also prefixes other ids; nothing matching raises a KeyError
naming the text; more than one match raises a ValueError listing the candidates.
"""
import pytest
from conftest import make_job_dir

from offload import jobs


def _make(root, *names):
    for name in names:
        make_job_dir(root, name, meta={"id": name})


def test_resolve_unique_prefix_returns_the_full_id(tmp_path):
    """A prefix that matches exactly one job id resolves to that id."""
    _make(tmp_path, "j20260101-alpha", "j20260102-beta")
    assert jobs.resolve_job_id(str(tmp_path), "j20260101-al") == "j20260101-alpha"


def test_resolve_no_match_raises_key_error_naming_the_text(tmp_path):
    """Nothing starts with the text -> a KeyError naming the text."""
    _make(tmp_path, "j20260101-alpha")
    with pytest.raises(KeyError) as excinfo:
        jobs.resolve_job_id(str(tmp_path), "zzz")
    assert "zzz" in str(excinfo.value)


def test_resolve_ambiguous_prefix_lists_the_candidates(tmp_path):
    """A prefix shared by more than one id -> a ValueError listing the candidates."""
    _make(tmp_path, "j20260101-alpha", "j20260101-alphabet")
    with pytest.raises(ValueError) as excinfo:
        jobs.resolve_job_id(str(tmp_path), "j20260101-al")
    message = str(excinfo.value)
    assert "j20260101-alpha" in message
    assert "j20260101-alphabet" in message


def test_resolve_exact_match_wins_over_longer_ids(tmp_path):
    """An exact match resolves to itself even when it prefixes other ids."""
    _make(tmp_path, "j20260101-alpha", "j20260101-alpha-2", "j20260101-alpha-3")
    assert jobs.resolve_job_id(str(tmp_path), "j20260101-alpha") == "j20260101-alpha"
