# Safety model

Offload lets language models edit code and run commands on your machine while you are not watching.
This page says what stops them, what does not, and what you should check yourself. Read the last
section even if you skip the rest.

## The short version

- Every model runs **inside a container**, as an unprivileged user, behind an outbound firewall it cannot change. Nothing a model does runs on your host.
- The **local model's container never holds your Claude login**. The paid worker's container gets it through
  the environment, never on a command line.
- The project's **tests run in a container with no network at all**, because tests are code the model just wrote.
- Workers get an **allowlist of tools**, not a blocklist. There is no `git push`, `ssh`, `docker`, `curl` or `pip` on it, and no `sudo` in the image.
- The engine, not a model, makes the one commit and the one push per job, to the repository the job names.
- Three kinds of action always **stop and ask you**: spending money, publishing, deleting outside the job's worktree.

## What runs where

| Thing | Where it runs | What it can reach |
|---|---|---|
| The daemon (`offload serve`) | your host, as your user | your files, Docker, your token file. It is about 1,700 lines of Python you can read. |
| Local worker (Claude Code harness → proxy → your model) | sandbox container | the job's worktree (read/write) and the proxy. Nothing on the internet. **No token.** |
| Paid worker (Claude Code → Anthropic) | sandbox container | the job's worktree, `api.anthropic.com`, your subscription token in its environment, a per-job session folder |
| The job's tests | sandbox container, `--network none` | the job's worktree. No network, no secrets. |
| Translation proxy | its own container | the model server only |
| Model server (llama.cpp) | its own container | loopback on the host, and the private Docker network |

## The firewall, and why a worker cannot change it

The container's entry point runs as root for one job: raise the outbound firewall. If that fails, it prints an
error and exits, and the worker never starts. Then it drops to an unprivileged user with **every capability
removed and no way to regain any** (`setpriv --bounding-set=-all --no-new-privs`), and only then runs the worker.
There is no `sudo` in the image. A model that tries `iptables -F` gets "permission denied".

The rules are default-deny on outbound traffic, for IPv4 and IPv6. Allowed: loopback, replies, DNS to the
container's own resolvers, the container's own Docker network (where the local model's proxy is), and:

- **paid worker:** `api.anthropic.com` on port 443. Nothing else. No GitHub, no npm, no PyPI.
- **local worker:** nothing beyond the Docker network. It cannot reach Anthropic or anything on the internet.
- **tests:** the container has no network interface at all.

The script ends by proving itself: `example.com` must be unreachable, and the allowed host must be reachable.
It is an address allowlist resolved when the container starts, not a content filter.

## Tools the workers may use

Claude Code's permission mode is `dontAsk` with an explicit `--allowedTools` list: reading and editing
files, and a short list of shell commands (`python3`, `pytest`, `git diff`, `git status`, `git log`, `ls`, `cat`;
the local worker also gets `head`, `tail`, `wc`, `grep`, `find`, `mkdir`, `sed`, `diff`). Anything else is
refused by the harness without a prompt. The lists are `claude_tools` and `local_tools` in the config.

## Gates

A job marked `public: true` stops before the push and asks you. The question goes to your Discord webhook and
to `offload status`; you answer with `offload answer <job> yes`. No answer within a day fails the job and
pushes nothing. Money and deletion use the same mechanism. No job type spends money today; the gate exists so
that adding one cannot skip it.

## What the engine does on your host, outside any container

This list is short on purpose, and it is the list to audit:

1. `git clone`, `checkout`, `reset --soft`, `add`, `commit`, `push` in the job's worktree, with `GIT_TERMINAL_PROMPT=0`.
2. `docker run` and `docker kill` for the containers above.
3. Reads your token file and passes it to one container's environment.
4. Posts text to your Discord webhook.
5. Reads and writes its own files under `~/.config/offload`, `~/.local/state/offload`, `~/.local/share/offload`.

If you set `run_tests_on_host: true`, the test command joins this list. Do not set it for a repository you do
not trust, and know that a model edits that repository.

## What this does not protect against

- **A malicious repository.** Git hooks do not run on clone, but a repo can carry build files and test files.
  Those run only inside containers, but they can still burn your model time or your Claude allowance.
- **Prompt injection through repository content.** A file can tell the model to do something else. The model
  can only act through the tool allowlist, inside the firewall, in one worktree. It can still write bad code.
  Review is a second model and the tests, not a guarantee. Read the diff before you merge.
- **Exfiltration to the one allowed host.** The paid worker can reach `api.anthropic.com` and nothing else, and
  its container holds your Claude token. What it reads from your worktree goes to Anthropic, as it does when you
  use Claude Code by hand. The local worker and the tests cannot reach the internet at all.
- **Docker itself.** Containers are not virtual machines. The container is started with `NET_ADMIN` and `NET_RAW`
  so its entry point can set the firewall; both are dropped before the worker runs. It never gets the Docker
  socket, host networking, or privileged mode.
- **Your own push credentials.** The engine pushes with whatever credentials your host's git has for the
  remote you named. It pushes one branch, `offload/<job id>`. It never pushes to a default branch.
- **The budget is a pacer, not a hard cap from your provider.** It stops starting Claude calls when you are
  ahead of pace. A single call in flight finishes.

## Reporting a problem

Open a private security advisory on the GitHub repository. Please do not open a public issue for a
vulnerability.
