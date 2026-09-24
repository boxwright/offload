"""Tests for the planner's config keys: plan_max_turns and plan_reads.

Every test points HOME at a fresh tmp_path and clears OFFLOAD_CONFIG, so none reads the real home directory.
"""
import os

import pytest

from offload import config as config_module


@pytest.fixture
def _isolated_config(monkeypatch, tmp_path):
    """The config module with HOME redirected and OFFLOAD_CONFIG cleared."""
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.delenv("OFFLOAD_CONFIG", raising=False)
    for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    return config_module


# ---------------------------------------------------------------- defaults
def test_plan_keys_default(_isolated_config):
    """With no config file, the planner gets 20 turns and full reads."""
    c = _isolated_config.load_config()
    assert c.plan_max_turns == 20
    assert c.plan_reads == "full"


# ---------------------------------------------------------------- overrides
def test_plan_keys_override(_isolated_config, tmp_path):
    """A config file overrides the planner keys; the rest keep defaults."""
    f = tmp_path / "cfg.yaml"
    f.write_text("plan_max_turns: 30\nplan_reads: index\n")
    c = _isolated_config.load_config(str(f))
    assert c.plan_max_turns == 30
    assert c.plan_reads == "index"
    assert c.step_timeout == 1200


# ---------------------------------------------------------------- validation
def test_plan_reads_rejects_a_bad_value_naming_it(_isolated_config, tmp_path):
    """plan_reads outside full/index raises a ValueError naming the bad value."""
    f = tmp_path / "bad.yaml"
    f.write_text("plan_reads: half\n")
    with pytest.raises(ValueError, match="plan_reads"):
        _isolated_config.load_config(str(f))
    f.write_text("plan_reads: Full\n")
    try:
        _isolated_config.load_config(str(f))
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "'Full'" in str(e)
