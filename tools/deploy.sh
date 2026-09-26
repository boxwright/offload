#!/bin/bash
# offload-deploy: put the box on `main` of its own bare repository, and nothing else.
# Usage, on the box:  offload-deploy            (deploys origin/main of ~/.local/share/offload/src)
# The source copy is a clone of the bare repository. No working tree is rsynced here by anyone.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SRC=$HOME/.local/share/offload/src
[ -d "$SRC/.git" ] || { echo "offload-deploy: $SRC is not a git clone; see docs/design/one-deployer.md" >&2; exit 2; }
git -C "$SRC" fetch -q origin main
before=$(git -C "$SRC" rev-parse --short HEAD)
git -C "$SRC" checkout -q main 2>/dev/null || git -C "$SRC" checkout -q -b main origin/main
git -C "$SRC" reset -q --hard origin/main
after=$(git -C "$SRC" rev-parse --short HEAD)
uv tool install --force "$SRC" 2>&1 | tail -1
systemctl --user restart offload.service
for _ in $(seq 1 10); do [ "$(systemctl --user is-active offload.service)" = active ] && break; sleep 3; done
state=$(systemctl --user is-active offload.service)
printf 'commit %s (was %s)\nat %s\nby %s@%s from %s\n' "$after" "$before" "$(date '+%F %T')" "$USER" "$(hostname)" "${SSH_CLIENT%% *}" > "$SRC/.deployed"
echo "deployed $after (was $before); service $state"
offload doctor | tail -1
