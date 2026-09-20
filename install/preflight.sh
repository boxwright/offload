#!/usr/bin/env bash
# preflight.sh — tell the user plainly whether this machine can run the engine, and what is missing.
# Read-only. Installs nothing. Exit 0 = ready, 1 = something required is missing.
set -u
ok=0; warn=0; fail=0
say()  { printf '%-9s %s\n' "$1" "$2"; }
PASS() { say "[ ok ]" "$1"; ok=$((ok+1)); }
WARN() { say "[warn]" "$1"; warn=$((warn+1)); }
FAIL() { say "[MISSING]" "$1"; fail=$((fail+1)); }

echo "== Machine"
os="$(uname -s)"; arch="$(uname -m)"
case "$os" in
  Linux)  PASS "Linux $arch ($(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-unknown distro}"))";;
  Darwin) WARN "macOS $arch: the engine daemon targets Linux. A Mac can run the local model (MLX) but is not a tested host yet.";;
  *)      FAIL "Unsupported OS: $os";;
esac
ram_gb=$( (awk '/MemTotal/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null) || true); [ -z "${ram_gb:-}" ] && ram_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
[ "${ram_gb:-0}" -ge 32 ] && PASS "System RAM: ${ram_gb} GB" || WARN "System RAM: ${ram_gb} GB. 32 GB or more is the tested floor."
free_gb=$(df -Pk "$HOME" | awk 'NR==2 {printf "%d", $4/1048576}')
[ "${free_gb:-0}" -ge 60 ] && PASS "Free disk in \$HOME: ${free_gb} GB" || FAIL "Free disk in \$HOME: ${free_gb} GB. The model (about 20 GB), the sandbox image (about 2.5 GB) and job worktrees need 60 GB free."

echo "== GPU (for the local model)"
if command -v nvidia-smi >/dev/null 2>&1; then
  line="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)"
  name="${line%%,*}"; vram_mb="$(echo "${line##*,}" | tr -d ' ')"; vram_gb=$(( ${vram_mb:-0} / 1024 ))
  if   [ "$vram_gb" -ge 30 ]; then PASS "GPU: $name, ${vram_gb} GB VRAM. Tested class (Qwen3.8-27B Q5, long context)."
  elif [ "$vram_gb" -ge 22 ]; then WARN "GPU: $name, ${vram_gb} GB VRAM. Should run Qwen3.8-27B at 4-bit with a shorter context. Untested by us."
  elif [ "$vram_gb" -ge 1 ];  then FAIL "GPU: $name, ${vram_gb} GB VRAM. Too small for the 27B model. A smaller model option is planned, not shipped."
  else FAIL "nvidia-smi is present but reports no GPU."; fi
elif [ "$os" = "Darwin" ] && [ "$arch" = "arm64" ]; then
  [ "${ram_gb:-0}" -ge 32 ] && WARN "Apple Silicon with ${ram_gb} GB unified memory: can serve a 4-bit 27B model via MLX. Untested as an engine host." \
                            || FAIL "Apple Silicon with ${ram_gb} GB unified memory: too small for the 27B model."
else
  FAIL "No NVIDIA GPU found (nvidia-smi missing). The point of this tool is a local model on your own GPU."
fi

echo "== Docker (the sandbox and the model server run in containers)"
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then PASS "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) reachable as $(id -un)"
  elif [ "$os" = "Darwin" ]; then FAIL "Docker is installed but not running. Start Docker Desktop."
  else FAIL "Docker is installed but $(id -un) cannot reach it. Fix: sudo usermod -aG docker $(id -un), then log out and in."; fi
  if docker info 2>/dev/null | grep -qi 'nvidia'; then PASS "NVIDIA container runtime registered with Docker"
  elif command -v nvidia-smi >/dev/null 2>&1; then FAIL "NVIDIA Container Toolkit not registered with Docker. The model server container needs it."; fi
else FAIL "Docker not installed."; fi

echo "== Claude Code (your own subscription; this tool never shares accounts)"
if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then PASS "Claude Code CLI: $( (claude --version 2>/dev/null || "$HOME/.local/bin/claude" --version 2>/dev/null) | head -1)"
else WARN "Claude Code CLI not found. The installer can add it (official installer from claude.ai)."; fi
tok="${XDG_CONFIG_HOME:-$HOME/.config}/offload/claude-token"
if [ -s "$tok" ]; then
  perms=$(stat -c '%a' "$tok" 2>/dev/null || stat -f '%Lp' "$tok"); [ "$perms" = "600" ] && PASS "Subscription token file present, private (600)" || WARN "Token file present but permissions are $perms. Fix: chmod 600 $tok"
else WARN "No subscription token yet. You create it once with: claude setup-token (needs a Claude Pro or Max plan)."; fi

echo "== Tools"
for t in git curl python3; do command -v $t >/dev/null 2>&1 && PASS "$t" || FAIL "$t not installed"; done
command -v uv >/dev/null 2>&1 && PASS "uv" || WARN "uv not installed. The installer can add it."

echo
echo "Result: $ok ok, $warn warnings, $fail missing."
[ "$fail" -eq 0 ] && { echo "This machine can run the engine."; exit 0; } || { echo "Fix the MISSING items first. Warnings are safe to install with, but read them."; exit 1; }
