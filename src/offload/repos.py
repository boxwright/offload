"""The repositories Offload may work on: `repos.yaml`, one line per repository, path or URL -> what it is."""
import json
import os

import yaml

from offload.config import get_config
from offload.sandbox import sh

HEADER = ("# Repositories Offload may work on, so a one-line `offload add` can name them loosely.\n"
          "#   <path or git URL>: <one line on what it is>\n")


def known_repos():
    """The mapping in `repos_file`, or an empty mapping when the file is missing.

    A file that does not parse raises ValueError naming the file and the line, so the caller can tell the
    owner in one sentence instead of a traceback.
    """
    path = get_config().repos_file
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" line {mark.line + 1}" if mark else ""
            raise ValueError(f"{path}{where} is not valid YAML: put the description in double quotes") from exc
    return data if isinstance(data, dict) else {}


def add(target, description):
    """Register a repository after `git ls-remote` proves it is reachable. Returns 0, or 1 with the reason printed."""
    if "://" not in target and not target.startswith("git@"):
        target = os.path.abspath(os.path.expanduser(target))          # one spelling per local repository
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    code, _, err, _ = sh(["git", "ls-remote", "--heads", target], timeout=60, env=env)
    if code != 0:
        print(f"not registered: git ls-remote failed for {target}: {err.strip()[-200:]}")
        return 1
    path = get_config().repos_file
    try:
        current = known_repos()
    except ValueError as exc:
        print(f"not registered: {exc}")
        return 1
    if target in current:
        print(f"already registered: {target}: {current[target]}")
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a") as f:
        if new_file:
            f.write(HEADER)
        f.write(f"{json.dumps(target)}: {json.dumps(description.strip())}\n")     # JSON strings are valid YAML
    print(f"registered {target}: {description.strip()}")
    return 0


def list_repos():
    """Print every registered repository. Returns 0, or 1 when the file does not parse."""
    try:
        current = known_repos()
    except ValueError as exc:
        print(str(exc))
        return 1
    if not current:
        print("no repositories registered; add one with: offload repo add <path-or-url> \"<what it is>\"")
        return 0
    for target, description in current.items():
        print(f"{target}: {description}")
    return 0
