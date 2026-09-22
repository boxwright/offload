"""First-run commands: `offload init` writes the files, `offload doctor` checks the pieces,
`offload demo` queues a two-minute job on a sample repository."""
import os
import shutil
import sys
import urllib.error
import urllib.request

from offload import config
from offload.config import get_config
from offload.files import write_text
from offload.sandbox import sh
from offload.templates import (
    DEFAULT_BUDGET,
    DEFAULT_CONFIG,
    DEFAULT_REPOS,
    DEMO_JOB,
    DEMO_MODULE,
    DEMO_TESTS,
    DIGEST_SERVICE_UNIT,
    DIGEST_TIMER_UNIT,
    SERVICE_UNIT,
)


def _offload_command():
    """How the service should start the daemon: the installed script if there is one, else this interpreter."""
    return shutil.which("offload") or f"{sys.executable} -m offload"


def _write_if_missing(path, text, mode=None):
    if os.path.exists(path):
        print(f"  kept     {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_text(path, text)
    if mode is not None:
        os.chmod(path, mode)
    print(f"  wrote    {path}")


def init(systemd=True):
    """Create the directories and starter files. Never overwrites a file that exists."""
    settings = get_config()
    for directory in (config.config_dir(), config.state_dir(), settings.jobs_root):
        os.makedirs(directory, exist_ok=True)
    os.chmod(config.config_dir(), 0o700)      # it will hold the token and the webhook
    _write_if_missing(config.default_config_path(), DEFAULT_CONFIG)
    _write_if_missing(settings.budget_file, DEFAULT_BUDGET)
    _write_if_missing(settings.repos_file, DEFAULT_REPOS)
    if systemd:
        units = os.path.expanduser("~/.config/systemd/user")
        command = _offload_command()
        _write_if_missing(os.path.join(units, "offload.service"), SERVICE_UNIT.format(offload=command))
        _write_if_missing(os.path.join(units, "offload-digest.service"), DIGEST_SERVICE_UNIT.format(offload=command))
        _write_if_missing(os.path.join(units, "offload-digest.timer"), DIGEST_TIMER_UNIT)
    print("\nNext:")
    if not os.path.exists(settings.token_file):
        print(f"  1. claude setup-token        then save the token it prints to {settings.token_file} (chmod 600)")
    print("  2. offload doctor            checks Docker, the sandbox image, the model and the token")
    print("  3. systemctl --user enable --now offload.service offload-digest.timer")
    print("  4. offload demo              a two-minute job, so you can watch it work")
    return 0


def _check(label, ok, detail=""):
    print(f"  [{'ok' if ok else 'MISSING'}] {label}{' — ' + detail if detail else ''}")
    return ok


def _http_ok(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _private(path):
    return os.path.exists(path) and (os.stat(path).st_mode & 0o077) == 0


def doctor():
    """Check every piece a job needs. Returns 0 when all required pieces are in place."""
    settings = get_config()
    docker_ok = sh(["docker", "info"], timeout=30)[0] == 0
    image_ok = docker_ok and sh(["docker", "image", "inspect", settings.sandbox_image], timeout=30)[0] == 0
    network_ok = docker_ok and sh(["docker", "network", "inspect", settings.docker_network], timeout=30)[0] == 0
    proxy_ok = False
    if image_ok and network_ok:
        probe = f"curl -fs -m 5 {settings.proxy_url}/health/liveliness >/dev/null"
        args = ["docker", "run", "--rm", "--network", settings.docker_network, "--cap-add=NET_ADMIN",
                "--cap-add=NET_RAW", "-e", "OFFLOAD_ALLOW_HOSTS=", settings.sandbox_image, probe]
        proxy_ok = sh(args, timeout=60)[0] == 0
    required = [
        _check("Docker reachable", docker_ok, "" if docker_ok else "start Docker, or add yourself to the docker group"),
        _check(f"sandbox image {settings.sandbox_image}", image_ok,
               "" if image_ok else "docker build -t it from sandbox/"),
        _check(f"Docker network {settings.docker_network}", network_ok, "" if network_ok else "start the model stack"),
        _check(f"local model proxy at {settings.proxy_url}", proxy_ok, "" if proxy_ok else "is the model stack up?"),
        _check(f"Claude token {settings.token_file}", _private(settings.token_file),
               "" if _private(settings.token_file) else "claude setup-token, save it there, chmod 600"),
        _check(f"budget file {settings.budget_file}", os.path.exists(settings.budget_file),
               "" if os.path.exists(settings.budget_file) else "offload init writes it"),
    ]
    webhook = os.path.exists(settings.webhook_file)
    print(f"  [{'ok' if webhook else 'optional'}] Discord webhook {settings.webhook_file}"
          f"{'' if webhook else ' — without it, gate questions only appear in `offload status`'}")
    print("\nready" if all(required) else "\nnot ready: fix the MISSING items")
    return 0 if all(required) else 1


def _git(args, cwd):
    code, _, err, _ = sh(["git", *args], cwd=cwd)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {err.strip()}")


def demo():
    """Create a small repository with one planted defect, and queue a job to fix it."""
    repo = os.path.join(config.data_dir(), "demo-calc")
    bare = f"{repo}.git"
    if not os.path.exists(bare):
        os.makedirs(os.path.join(repo, "calc"))
        os.makedirs(os.path.join(repo, "tests"))
        write_text(os.path.join(repo, "calc", "__init__.py"), DEMO_MODULE)
        write_text(os.path.join(repo, "tests", "test_calc.py"), DEMO_TESTS)
        write_text(os.path.join(repo, "README.md"), "# demo-calc\n\nA sample repository for `offload demo`.\n")
        _git(["init", "-q", "-b", "main"], repo)
        _git(["-c", "user.name=offload", "-c", "user.email=offload@localhost", "add", "-A"], repo)
        _git(["-c", "user.name=offload", "-c", "user.email=offload@localhost", "commit", "-q", "-m",
              "demo repository with one failing statistic"], repo)
        _git(["clone", "-q", "--bare", repo, bare], None)
        shutil.rmtree(repo)
    index = 1
    while os.path.exists(os.path.join(get_config().jobs_root, f"demo-{index:03d}")):
        index += 1
    job_id = f"demo-{index:03d}"
    job_dir = os.path.join(get_config().jobs_root, job_id)
    os.makedirs(job_dir)
    write_text(os.path.join(job_dir, "job.md"), DEMO_JOB.format(job_id=job_id, repo=bare))
    print(f"queued {job_id}. Watch it with:  offload status     then:  offload report {job_id}")
    return 0
