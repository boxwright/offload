"""Configuration: every machine-specific value in one place.

`load_config(path=None)` layers a YAML file over the built-in defaults. It reads the first of:

    1. the explicit `path` argument
    2. the file named by the OFFLOAD_CONFIG environment variable
    3. ~/.config/offload/config.yaml   (or under $XDG_CONFIG_HOME)
    4. nothing: the defaults

`~` and `$VAR` are expanded in every string value. A key the Config does not have raises a
ValueError that names it. PyYAML is only imported when a file exists.

Default locations follow the XDG base directories: settings and secrets under ~/.config/offload,
the ledger and the pause file under ~/.local/state/offload, jobs under ~/.local/share/offload.

`get_config()` returns the current Config, loading it on the first call.
`set_config(config)` installs a Config, or None to load again on the next call. It is for tests, and for a
long-running process that wants to re-read the file.
"""
import dataclasses
import os
from dataclasses import dataclass, field

CONFIG_ENV = "OFFLOAD_CONFIG"

READ_ONLY_TOOLS = "Read,Glob,Grep"
EDIT_TOOLS = "Edit,Write"
SAFE_SHELL_TOOLS = ("Bash(python3 *),Bash(python *),Bash(pytest *),Bash(git diff *),Bash(git status *),"
                    "Bash(git log *),Bash(ls *),Bash(cat *)")
LOCAL_SHELL_TOOLS = ("Bash(head *),Bash(tail *),Bash(wc *),Bash(grep *),Bash(find *),Bash(mkdir *),"
                     "Bash(sed *),Bash(diff *)")


def _xdg(env_name, fallback):
    base = os.environ.get(env_name) or os.path.expanduser(fallback)
    return os.path.join(base, "offload")


def config_dir():
    return _xdg("XDG_CONFIG_HOME", "~/.config")


def state_dir():
    return _xdg("XDG_STATE_HOME", "~/.local/state")


def data_dir():
    return _xdg("XDG_DATA_HOME", "~/.local/share")


def _in(directory, name):
    return field(default_factory=lambda: os.path.join(directory(), name))


@dataclass(frozen=True)
class Config:
    """The engine's settings. Immutable once loaded."""

    # Where things live.
    jobs_root: str = _in(data_dir, "jobs")
    budget_file: str = _in(config_dir, "budget.yaml")
    repos_file: str = _in(config_dir, "repos.yaml")             # repositories intake may choose from
    claude_auth: str = "subscription"                            # subscription (token_file) or api_key (api_key_file)
    token_file: str = _in(config_dir, "claude-token")           # from `claude setup-token`; chmod 600
    api_key_file: str = _in(config_dir, "anthropic-api-key")    # an Anthropic API key; billed per call; chmod 600
    webhook_file: str = _in(config_dir, "discord-webhook")      # optional; chmod 600
    notifier: str = "discord"                                   # discord, ntfy, or none
    ntfy_url: str = ""                                          # the full topic URL, for example https://ntfy.sh/<topic>
    ntfy_token_file: str = _in(config_dir, "ntfy-token")        # optional; chmod 600
    ledger: str = _in(state_dir, "ledger.jsonl")
    pause_file: str = _in(state_dir, "PAUSE")

    # The sandbox and the local model.
    sandbox_image: str = "offload-sandbox:latest"
    docker_network: str = "offload_net"                          # the network the proxy is on
    proxy_url: str = "http://offload-proxy:4000"                 # the proxy, as seen from that network
    claude_allow_hosts: str = "api.anthropic.com"                # all the paid worker may reach, space separated
    local_model_name: str = "local-model"                        # the model name the proxy exposes
    local_max_turns: int = 40
    sandbox_memory: str = "4g"                                   # hard cap per worker container; swap is not allowed
    sandbox_cpus: float = 2.0                                    # CPU cores per worker container
    sandbox_pids: int = 512                                      # process cap per worker container
    claude_tools: str = f"{READ_ONLY_TOOLS},{EDIT_TOOLS},{SAFE_SHELL_TOOLS}"
    local_tools: str = f"{READ_ONLY_TOOLS},{EDIT_TOOLS},{SAFE_SHELL_TOOLS},{LOCAL_SHELL_TOOLS}"

    # How jobs run.
    git_user_name: str = "offload"                               # the author of the one commit per job
    git_user_email: str = "offload@localhost"
    run_tests_on_host: bool = False                              # True runs the test command outside the sandbox
    host_test_path: str = ""                                     # prepended to PATH when run_tests_on_host is true
    step_timeout: int = 1200
    max_test_fails: int = 3
    gate_wait_s: int = 86400
    keep_days: int = 14              # finished jobs older than this lose work/, claude-home/ and scratch/; 0 = off


def _expand(value):
    """expanduser + expandvars on a string; anything else passes through."""
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    return value


def default_config_path():
    return os.path.join(config_dir(), "config.yaml")


def _candidate_path(path):
    """The config file to read, or None when there is none."""
    candidates = [path, os.environ.get(CONFIG_ENV), default_config_path()]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _read_yaml(path):
    try:
        import yaml
    except ImportError as exc:
        raise ValueError(f"PyYAML is required to read {path!r}: pip install pyyaml") from exc
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def load_config(path=None):
    """Build a Config from the first config file found, else from the defaults."""
    defaults = dataclasses.asdict(Config())
    file_path = _candidate_path(path)
    overrides = _read_yaml(file_path) if file_path else {}
    unknown = sorted(set(overrides) - set(defaults))
    if unknown:
        raise ValueError(
            f"unknown config key(s) in {file_path!r}: {', '.join(unknown)}; "
            f"known keys: {', '.join(sorted(defaults))}"
        )
    values = {key: _expand(value) for key, value in {**defaults, **overrides}.items()}
    return Config(**values)


_config = None


def get_config():
    """Return the current Config, loading it on the first call."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config):
    """Make `config` the current Config and return the previous one. None means: load again on the next call.

    For tests, and for a long-running process that wants to re-read the file.
    """
    global _config
    previous = _config
    _config = config
    return previous
