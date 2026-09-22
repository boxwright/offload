"""Running commands inside the sandbox container.

Both workers use the same container image and the same command line. They differ in the environment
they get (a subscription token, or the address of the local model's proxy), the tools they may use,
and what is mounted.
"""
import grp
import json
import os
import shlex
import subprocess
import time
import uuid

from offload.config import get_config

FIREWALL_FAILED = "FIREWALL_FAILED"
WORKER_LABEL = "offload.role=worker"     # on every container the engine starts, so leftovers can be found

class SandboxError(RuntimeError):
    """The sandbox itself failed, as opposed to the worker inside it."""


def sh(cmd, cwd=None, timeout=600, env=None):
    """Run a command. Returns (exit code, stdout, stderr, wall seconds)."""
    started = time.time()
    done = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True,
                          timeout=timeout, env=env)
    return done.returncode, done.stdout, done.stderr, round(time.time() - started, 1)


def _group_names():
    names = set()
    for gid in os.getgroups():
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:        # a numeric group with no entry (LDAP, containers)
            continue
    return names


def _with_docker_group(cmd):
    """Run through `sg docker` when this process is not in the docker group.

    A systemd user manager that started before the user joined the group never picks it up.
    """
    if "docker" in _group_names():
        return cmd
    return ["sg", "docker", "-c", shlex.join(cmd)]


def claude_cmdline(prompt, model, tools, max_turns, resume=None):
    """The `claude -p` command line, as one shell string."""
    parts = ["claude", "-p", shlex.quote(prompt)]
    if resume:
        parts += ["--resume", shlex.quote(resume)]
    parts += ["--model", model, "--permission-mode", "dontAsk", "--allowedTools", shlex.quote(tools),
              "--output-format", "json", "--max-turns", str(max_turns), "<", "/dev/null"]
    return " ".join(parts)


def parse_cli_json(stdout, stderr):
    """Claude Code prints one JSON record last. Anything else becomes an error record."""
    try:
        return json.loads(stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"is_error": True, "result": (stdout + stderr)[-500:]}


def _docker_run(args, inner, timeout, secret_env=None):
    """`docker run --rm <args> IMAGE <inner>`. The image's entry point raises the firewall, drops privileges,
    and runs `inner`. A timeout kills the container and returns exit code 124."""
    name = f"offload-{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", name, "--label", WORKER_LABEL, *args, get_config().sandbox_image, inner]
    process_env = {**os.environ, **(secret_env or {})}
    try:
        return sh(_with_docker_group(cmd), timeout=timeout, env=process_env)
    except subprocess.TimeoutExpired:
        sh(_with_docker_group(["docker", "kill", name]), timeout=60)
        return 124, "", f"TIMEOUT: did not finish in {timeout} s", float(timeout)


def kill_leftover_containers():
    """Kill worker containers that outlived a daemon: a stopped daemon takes the docker client with it, not
    the container. One daemon runs on a host, so at its start every labelled container is a leftover.
    Returns the number killed."""
    code, out, _, _ = sh(_with_docker_group(["docker", "ps", "-q", "--filter", f"label={WORKER_LABEL}"]), timeout=60)
    ids = out.split() if code == 0 else []
    if ids:
        sh(_with_docker_group(["docker", "kill", *ids]), timeout=60)
    return len(ids)


def run_sandbox(inner, env, mounts, secret_env=None, timeout=None):
    """Run a Claude Code command line in a fresh, firewalled container.

    Returns (reply record, exit code, stderr, wall seconds). `env` is passed on the command line.
    `secret_env` is passed through this process's environment instead, so the values never appear in
    a process list.
    """
    args = ["--network", get_config().docker_network, "--cap-add=NET_ADMIN", "--cap-add=NET_RAW"]
    for key, value in env.items():
        args += ["-e", f"{key}={value}"]
    for key in secret_env or {}:
        args += ["-e", key]
    for host_path, container_path in mounts:
        args += ["-v", f"{host_path}:{container_path}"]
    code, out, err, wall = _docker_run(args, inner, timeout or get_config().step_timeout, secret_env)
    if code == 124 and err.startswith("TIMEOUT"):
        return {"is_error": True, "result": err}, code, "", wall
    reply = parse_cli_json(out, err)
    if str(reply.get("result", "")).startswith(FIREWALL_FAILED):
        raise SandboxError(reply["result"])
    return reply, code, err, wall


def run_shell_in_sandbox(command, workdir, timeout=600):
    """Run a shell command on the worktree in a container with no network and no secrets.

    This is how the job's tests run: code a worker wrote never executes on the host.
    Returns (exit code, stdout, stderr, wall seconds).
    """
    args = ["--network", "none", "-e", "OFFLOAD_NO_NETWORK=1", "-v", f"{workdir}:/workspace"]
    return _docker_run(args, command, timeout)
