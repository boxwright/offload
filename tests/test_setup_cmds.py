"""Tests for `offload init` and `offload demo`. Both run against a temporary home."""
import dataclasses
import os
import subprocess

import pytest

from offload import config, setup_cmds, templates


@pytest.fixture
def temp_install(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("OFFLOAD_CONFIG", raising=False)
    previous = config.set_config(config.load_config())
    yield tmp_path
    config.set_config(previous)


def test_init_writes_starter_files_and_keeps_existing_ones(temp_install, capsys):
    assert setup_cmds.init(systemd=False) == 0
    budget = temp_install / "cfg" / "offload" / "budget.yaml"
    assert budget.exists() and (temp_install / "cfg" / "offload" / "repos.yaml").exists()
    assert (temp_install / "data" / "offload" / "jobs").is_dir()
    assert oct(os.stat(temp_install / "cfg" / "offload").st_mode & 0o777) == "0o700"
    budget.write_text("claude: {allowance_percent: 10}\n")
    setup_cmds.init(systemd=False)
    assert budget.read_text() == "claude: {allowance_percent: 10}\n"
    assert "kept" in capsys.readouterr().out


def test_default_budget_is_valid_yaml_with_the_keys_the_pacer_reads():
    import yaml
    budget = yaml.safe_load(templates.DEFAULT_BUDGET)
    assert {"weekly_usd_equivalent", "allowance_percent", "week_resets", "models"} <= set(budget["claude"])
    assert set(budget["escalate_when"]) == {"failed_test_iterations", "no_progress_turns"}


def test_demo_builds_a_failing_repo_and_queues_jobs(temp_install):
    assert setup_cmds.demo() == 0 and setup_cmds.demo() == 0
    jobs_root = temp_install / "data" / "offload" / "jobs"
    assert sorted(p.name for p in jobs_root.iterdir()) == ["demo-001", "demo-002"]
    bare = temp_install / "data" / "offload" / "demo-calc.git"
    clone = temp_install / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    failing = subprocess.run(["python3", "-m", "pytest", "-q"], cwd=clone, capture_output=True, text=True)
    assert failing.returncode != 0 and "2 failed, 4 passed" in failing.stdout


def test_config_is_frozen_in_setup_too(temp_install):
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.get_config().jobs_root = "x"
