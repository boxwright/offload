"""Tests for offload.config: defaults, file overrides, lookup order, expansion, unknown keys.

Every test points HOME at a fresh tmp_path and clears OFFLOAD_CONFIG, so none reads the real home directory.
"""
import dataclasses
import os
import sys

import pytest

from offload import config as config_module

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def _isolated_config(monkeypatch, tmp_path):
    """The config module with HOME redirected and OFFLOAD_CONFIG cleared."""
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))
    monkeypatch.delenv("OFFLOAD_CONFIG", raising=False)
    for name in ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    return config_module


# ---------------------------------------------------------------- defaults
def test_defaults_match_today_constants(_isolated_config):
    """With no config file anywhere, the defaults follow the XDG directories under the (redirected) home."""
    c = _isolated_config.load_config()
    home = os.path.expanduser("~")
    assert c.jobs_root == os.path.join(home, ".local/share/offload/jobs")
    assert c.budget_file == os.path.join(home, ".config/offload/budget.yaml")
    assert c.repos_file == os.path.join(home, ".config/offload/repos.yaml")
    assert c.token_file == os.path.join(home, ".config/offload/claude-token")
    assert c.webhook_file == os.path.join(home, ".config/offload/discord-webhook")
    assert c.ledger == os.path.join(home, ".local/state/offload/ledger.jsonl")
    assert c.pause_file == os.path.join(home, ".local/state/offload/PAUSE")
    assert c.sandbox_image == "offload-sandbox:latest"
    assert c.docker_network == "offload_net"
    assert c.proxy_url == "http://offload-proxy:4000"
    assert "Bash(pytest *)" in c.claude_tools and "Bash(sed *)" not in c.claude_tools
    assert "Bash(sed *)" in c.local_tools
    assert (c.step_timeout, c.max_test_fails, c.gate_wait_s) == (1200, 3, 86400)
    assert c.run_tests_on_host is False


def test_xdg_variables_move_the_defaults(_isolated_config, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    c = _isolated_config.load_config()
    assert c.token_file == str(tmp_path / "cfg" / "offload" / "claude-token")
    assert c.ledger == str(tmp_path / "state" / "offload" / "ledger.jsonl")


def test_config_is_frozen(_isolated_config):
    """Config is a frozen dataclass: attribute assignment raises."""
    c = _isolated_config.load_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.step_timeout = 1


# ---------------------------------------------------------------- file overrides
def test_file_override_per_key(_isolated_config, tmp_path, monkeypatch):
    """A config file overrides exactly the keys it names; the rest keep defaults."""
    monkeypatch.setenv("OFFLOAD_CONFIG", str(tmp_path / "nope.yaml"))  # absent -> explicit path used
    f = tmp_path / "cfg.yaml"
    f.write_text("step_timeout: 999\nsandbox_image: myimg:dev\nledger: /tmp/led.jsonl\n")
    c = _isolated_config.load_config(str(f))
    assert c.step_timeout == 999
    assert c.sandbox_image == "myimg:dev"
    assert c.ledger == "/tmp/led.jsonl"
    # untouched keys keep their defaults
    assert c.token_file == os.path.join(os.path.expanduser("~"), ".config/offload/claude-token")
    assert c.max_test_fails == 3
    assert c.docker_network == "offload_net"


# ---------------------------------------------------------------- lookup order
def test_config_env_lookup(_isolated_config, tmp_path, monkeypatch):
    """OFFLOAD_CONFIG pointing at an existing file is used when no path is given."""
    f = tmp_path / "env.yaml"
    f.write_text("max_test_fails: 7\n")
    monkeypatch.setenv("OFFLOAD_CONFIG", str(f))
    c = _isolated_config.load_config()
    assert c.max_test_fails == 7


def test_explicit_path_beats_env(_isolated_config, tmp_path, monkeypatch):
    """An explicit path wins over the OFFLOAD_CONFIG env var."""
    env_f = tmp_path / "env.yaml"
    env_f.write_text("max_test_fails: 7\n")
    path_f = tmp_path / "explicit.yaml"
    path_f.write_text("max_test_fails: 11\n")
    monkeypatch.setenv("OFFLOAD_CONFIG", str(env_f))
    c = _isolated_config.load_config(str(path_f))
    assert c.max_test_fails == 11


def test_home_config_yaml_is_used_when_it_exists(_isolated_config, tmp_path):
    """~/.config/offload/config.yaml is picked up when no path and no env var."""
    home_cfg = tmp_path / ".config" / "offload" / "config.yaml"
    home_cfg.parent.mkdir(parents=True)
    home_cfg.write_text("max_test_fails: 5\n")
    c = _isolated_config.load_config()
    assert c.max_test_fails == 5


# ---------------------------------------------------------------- expansion
def test_tilde_and_var_expansion(_isolated_config, tmp_path, monkeypatch):
    """~ and $VAR are expanded in file values."""
    f = tmp_path / "cfg.yaml"
    f.write_text("ledger: ~/expanded/led.jsonl\npause_file: $TESTCFG_DIR/PAUSE\n")
    monkeypatch.setenv("TESTCFG_DIR", "/tmp/expanded")
    c = _isolated_config.load_config(str(f))
    assert c.ledger == os.path.expanduser("~/expanded/led.jsonl")
    assert c.pause_file == "/tmp/expanded/PAUSE"


def test_expansion_applies_to_defaults_too(_isolated_config):
    """Defaults are expanded as well (they contain ~), so a no-file load is absolute."""
    c = _isolated_config.load_config()
    assert not c.ledger.startswith("~")
    assert not c.pause_file.startswith("~")
    assert not c.token_file.startswith("~")


# ---------------------------------------------------------------- no PyYAML
def test_config_file_without_pyyaml_raises_one_clear_error(_isolated_config, tmp_path, monkeypatch):
    """A config file exists but PyYAML is missing: a ValueError that says what to install."""
    monkeypatch.setitem(sys.modules, "yaml", None)   # makes `import yaml` raise ImportError
    f = tmp_path / "cfg.yaml"
    f.write_text("step_timeout: 5\n")
    with pytest.raises(ValueError, match="PyYAML"):
        _isolated_config.load_config(str(f))


def test_defaults_need_no_pyyaml(_isolated_config, monkeypatch):
    """With no config file, the defaults load even when PyYAML is missing."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert _isolated_config.load_config().step_timeout == 1200


# ---------------------------------------------------------------- unknown keys
def test_unknown_key_raises_value_error_naming_key(_isolated_config, tmp_path):
    """A key the Config does not have raises a ValueError naming that key."""
    f = tmp_path / "bad.yaml"
    f.write_text("bogus_key: 1\n")
    try:
        _isolated_config.load_config(str(f))
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "bogus_key" in str(e)


def test_unknown_key_message_lists_known_keys(_isolated_config, tmp_path):
    """The ValueError message also lists the known keys for discoverability."""
    f = tmp_path / "bad.yaml"
    f.write_text("nope: 1\n")
    try:
        _isolated_config.load_config(str(f))
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "step_timeout" in str(e) and "docker_network" in str(e)
