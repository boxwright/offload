#!/usr/bin/env bash
# Offload installer. One command, and it asks before anything large or irreversible.
#   curl -fsSL https://raw.githubusercontent.com/boxwright/offload/main/install/install.sh | bash
# Flags: --yes (accept defaults), --no-model (skip the model download), --model q5|q4 (pick the build), --spec on|off (speculative decoding; default: ask, with a recommendation)
set -euo pipefail
REPO="${OFFLOAD_REPO:-https://github.com/boxwright/offload}"
HOME_DIR="${OFFLOAD_HOME:-$HOME/.local/share/offload}"   # the code, the model file and the stack env
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/offload"
HF="https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/resolve/main"
YES=0; NO_MODEL=0; PICK=""; SPEC=""; prev=""
for a in "$@"; do case "$a" in --yes) YES=1;; --no-model) NO_MODEL=1;; q5|q4) PICK="$a";; on|off) [ "$prev" = "--spec" ] && SPEC="$a";; esac; prev="$a"; done
ask() { [ "$YES" = 1 ] && return 0; read -r -p "$1 [y/N] " r </dev/tty; [[ "$r" =~ ^[Yy] ]]; }
step() { printf '\n== %s\n' "$1"; }

step "1/7 Get the code"
mkdir -p "$HOME_DIR"/models "$CONFIG_DIR"; chmod 700 "$CONFIG_DIR"
if [ -d "$HOME_DIR/src/.git" ]; then git -C "$HOME_DIR/src" pull -q --ff-only; else git clone -q --depth 1 "$REPO" "$HOME_DIR/src"; fi

step "2/7 Check this machine (read-only)"
bash "$HOME_DIR/src/install/preflight.sh" || { echo; echo "Preflight found missing requirements. Nothing was installed beyond the code in $HOME_DIR/src."; exit 1; }

step "3/7 Tools"
command -v uv >/dev/null 2>&1 || { ask "Install uv (Python tool runner, from astral.sh)?" && curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH="$HOME/.local/bin:$PATH"
command -v claude >/dev/null 2>&1 || { ask "Install the Claude Code CLI (official installer from claude.ai)?" && curl -fsSL https://claude.ai/install.sh | bash; }
uv tool install --force "$HOME_DIR/src" >/dev/null && echo "installed the offload command"

step "4/7 The local model"
vram_mb=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
vram_gb=$(( vram_mb / 1024 )); vram_exact=$(python3 -c "print(round($vram_mb/1024, 1))")
[ -z "$PICK" ] && { [ "$vram_gb" -ge 30 ] && PICK=q5 || PICK=q4; }
case "$PICK" in q5) FILE="Qwen3.8-27B-UD-Q5_K_XL.gguf"; SIZE="20 GB"; CTX=131072;; q4) FILE="Qwen3.8-27B-UD-Q4_K_XL.gguf"; SIZE="17 GB"; CTX=32768;; esac
echo "GPU memory: ${vram_gb} GB → $FILE (Apache-2.0, from Hugging Face, $SIZE), context $CTX tokens."
[ "$PICK" = q4 ] && echo "Note: the 4-bit build on a 24 GB card is untested by us. Tell us how it goes."
if [ "$NO_MODEL" = 0 ] && [ ! -s "$HOME_DIR/models/$FILE" ]; then
  ask "Download $SIZE to $HOME_DIR/models now?" && curl -fL --retry 5 -C - -o "$HOME_DIR/models/$FILE" "$HF/$FILE"
fi

step "4b/7 Speculative decoding (optional speed-up)"
# The model ships its own multi-token-prediction head. With --spec-type draft-mtp the server drafts several tokens
# per step and verifies them: output is bit-identical, decoding is 1.6x-2.5x faster (measured on an RTX 5090:
# 67 tok/s -> 104-169 tok/s). The cost is GPU memory: about 1.5 GB more. System RAM does not matter for this.
file_gb=$( [ "$PICK" = q5 ] && echo 20.2 || echo 17.0 )
read -r need head verdict <<<"$(python3 - "$vram_exact" "$file_gb" "$CTX" <<'PY'
import sys
vram, file_gb, ctx = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
usable = vram - 1.0                      # the driver and the desktop keep about 1 GB
kv = ctx / 1000 * 0.035                  # measured: 6.8 GB of KV at 196k context with q8 cache on this hybrid model
base = file_gb + kv + 1.0                # weights + KV + compute buffers
head = usable - (base + 1.5)             # what is left after the speculative head
print(f"{base + 1.5:.1f} {head:.1f} {'recommended' if head >= 1.0 else 'not-recommended'}")   # calibrated: predicts 29.6 GB where we measured 29.2 GB
PY
)"
echo "Estimated GPU memory with it on: ${need} GB of ${vram_exact} GB. Headroom: ${head} GB → ${verdict/-/ }."
[ "$verdict" = "not-recommended" ] && echo "With under 1 GB of headroom a long prompt can run the GPU out of memory. You can turn it on later and lower the context instead."
echo "(The memory figures are estimates scaled from one measured machine. The speed-up is measured.)"
if [ -z "$SPEC" ]; then
  if [ "$verdict" = recommended ]; then ask "Turn on speculative decoding (recommended)?" && SPEC=on || SPEC=off
  else ask "Turn on speculative decoding anyway (not recommended on this GPU)?" && SPEC=on || SPEC=off; fi
fi
SPEC_ARGS=""; [ "$SPEC" = on ] && SPEC_ARGS="--spec-type draft-mtp"
echo "speculative decoding: $SPEC"

step "5/7 Containers: model server, proxy, sandbox"
cat > "$HOME_DIR/stack.env" <<ENV
OFFLOAD_HOME=$HOME_DIR
OFFLOAD_MODEL_FILE=$FILE
OFFLOAD_CONTEXT=$CTX
OFFLOAD_SPEC_ARGS=$SPEC_ARGS
ENV
docker build -q -t offload-sandbox:latest "$HOME_DIR/src/sandbox" >/dev/null && echo "built the sandbox image"
docker compose --env-file "$HOME_DIR/stack.env" -f "$HOME_DIR/src/install/compose.yaml" up -d --build
echo "waiting for the model to load (first start reads $SIZE from disk)…"
for i in $(seq 1 60); do curl -fs http://127.0.0.1:8080/health >/dev/null 2>&1 && break; sleep 5; done
curl -fs http://127.0.0.1:8080/health >/dev/null && echo "model server is up" || { echo "The model server did not come up. See: docker logs offload-model"; exit 1; }

step "6/7 Your accounts (the installer never sees these values)"
if [ ! -s "$CONFIG_DIR/claude-token" ]; then
  echo "Run this yourself, approve in the browser, then save the token it prints:"
  echo "    claude setup-token"
  echo "    (umask 077; read -rs T; printf %s \"\$T\" > $CONFIG_DIR/claude-token)"
fi
[ -s "$CONFIG_DIR/discord-webhook" ] || echo "Optional, for gate questions and the daily digest: save a Discord webhook URL to $CONFIG_DIR/discord-webhook (chmod 600)."

step "7/7 Service"
offload init
offload doctor || { echo; echo "Finish the MISSING items above, then: systemctl --user enable --now offload.service offload-digest.timer"; exit 0; }
systemctl --user enable --now offload.service offload-digest.timer && echo "the offload service is running"
echo; echo "Done. Try:   offload demo      (a two-minute job on a sample repo, so you can watch it work)"
echo "Then:        offload add \"<one line about a change you want in one of your repos>\""
