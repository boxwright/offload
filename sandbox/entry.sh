#!/usr/bin/env bash
# Container entry point. Usage: offload-entry "<shell command>"
#   1. As root: raise the outbound firewall. If it fails, print an error record and stop. The command never runs.
#      OFFLOAD_NO_NETWORK=1 skips this; the engine sets it only for containers started with --network none.
#   2. Drop to the owner of /workspace with no capabilities and no way to regain them, then run the command.
set -uo pipefail

if [ "${OFFLOAD_NO_NETWORK:-}" != "1" ] && ! /usr/local/sbin/offload-firewall > /tmp/offload-firewall.log 2>&1; then
  echo '{"is_error": true, "result": "FIREWALL_FAILED: the sandbox firewall did not start, so the worker was not run"}'
  exit 97
fi

uid="$(stat -c %u /workspace)"
gid="$(stat -c %g /workspace)"
if [ "$uid" = "0" ]; then
  uid="$(id -u worker)"
  gid="$(id -g worker)"
fi
chown "$uid:$gid" /home/worker/.claude 2>/dev/null || true

cd /workspace
exec setpriv --reuid="$uid" --regid="$gid" --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs \
  env HOME=/home/worker USER=worker PATH="/home/worker/.local/bin:$PATH" bash -c "$1"
