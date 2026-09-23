#!/bin/bash
# run_harness.sh <work_root> <docker network> <proxy url> <label>
# Run every calibration task on a local model through the real path: Claude Code's harness inside the Offload
# sandbox, pointed at the translation proxy. Fresh container and session per task. Then score.
# Example: run_harness.sh /tmp/cal offload_net http://offload-proxy:4000 qwen3-coder-30b
set -u
ROOT="${1:?work_root}"; NET="${2:?docker network}"; PROXY="${3:?proxy url}"; LABEL="${4:?label}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="Read,Glob,Grep,Edit,Write,Bash(python3 *),Bash(python *),Bash(pytest *),Bash(git diff *),Bash(git status *),Bash(git log *),Bash(ls *),Bash(cat *),Bash(head *),Bash(tail *),Bash(wc *),Bash(grep *),Bash(find *),Bash(mkdir *),Bash(sed *),Bash(diff *)"
mkdir -p "$ROOT"
for src in "$HERE"/tasks/t*_*; do
  name=$(basename "$src"); dst="$ROOT/$name"; rm -rf "$dst"; cp -r "$src" "$dst"
  brief=$(cat "$dst/TASK.md")
  inner="claude -p $(printf %q "$brief") --model local-model --permission-mode dontAsk --allowedTools $(printf %q "$TOOLS") --output-format json --max-turns 40 < /dev/null"
  t0=$(date +%s.%N)
  timeout 1200 docker run --rm --network "$NET" --cap-add=NET_ADMIN --cap-add=NET_RAW \
    --memory 4g --memory-swap 4g --cpus 2 --pids-limit 512 --security-opt no-new-privileges \
    -e ANTHROPIC_BASE_URL="$PROXY" -e ANTHROPIC_AUTH_TOKEN=local -e ANTHROPIC_MODEL=local-model \
    -e ANTHROPIC_SMALL_FAST_MODEL=local-model -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 -e OFFLOAD_ALLOW_HOSTS= \
    -v "$dst:/workspace" offload-sandbox:latest "$inner" > "$dst/claude.json" 2> "$dst/claude.err"; rc=$?
  t1=$(date +%s.%N)
  python3 - "$t0" "$t1" "$rc" "$dst" <<'PY' > "$dst/run.json"
import sys, json
t0, t1, rc, dst = sys.argv[1:]
d = {}
try:
    lines = open(f"{dst}/claude.json").read().strip().splitlines()
    d = json.loads(lines[-1]) if lines else {}
except Exception as e:
    d = {"parse_error": str(e)[:100]}
u = d.get("usage", {}) or {}
json.dump({"wall_s": round(float(t1) - float(t0), 1), "exit": int(rc), "num_turns": d.get("num_turns"),
           "is_error": d.get("is_error"), "terminal_reason": d.get("terminal_reason"),
           "output_tokens": u.get("output_tokens"), "result_head": str(d.get("result"))[:100]}, sys.stdout)
PY
  echo "$name done rc=$rc wall=$(python3 -c "print(round($t1-$t0,1))")s"
done
# Score inside the sandbox with no network: the tests execute code the model just wrote, and the host may lack pytest.
cp "$HERE/score.py" "$HERE/tests.sha256.json" "$ROOT/"
docker run --rm --network none -e OFFLOAD_NO_NETWORK=1 --memory 2g --memory-swap 2g --cpus 2 --pids-limit 256 \
  --security-opt no-new-privileges -v "$ROOT:/workspace" offload-sandbox:latest "python3 /workspace/score.py /workspace $LABEL"
