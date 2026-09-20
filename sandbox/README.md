# Sandbox

The container every worker call and every test run happens in. Three files, all written for this project:

- `Dockerfile`: Python (for your project's tests), git, iptables, and Claude Code from Anthropic's installer,
  downloaded when you build the image. Claude Code is not part of this repository.
- `entry.sh`: runs as root only long enough to raise the firewall, then drops to an unprivileged user with every
  capability removed and `no-new-privs` set, and runs the command. If the firewall fails, the command never runs.
- `firewall.sh`: default-deny outbound, IPv4 and IPv6. Allows loopback, replies, DNS to the container's resolvers,
  the container's own Docker network, and the hosts in `OFFLOAD_ALLOW_HOSTS`. Then it proves both halves:
  `example.com` must be unreachable, the allowed host must be reachable.

The engine uses three profiles: the paid worker may reach `api.anthropic.com` only; the local worker may reach
nothing beyond the Docker network; tests run with `--network none`.

Build: `docker build -t offload-sandbox:latest sandbox/`. Add your project's toolchain to the Dockerfile if its
tests need more than Python.
