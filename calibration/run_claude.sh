#!/bin/bash
# run_claude.sh <work_root> <model> — run every calibration task on Claude Code headless (your own plan), fresh session per task.
set -u
ROOT="${1:?work_root}"; MODEL="${2:-sonnet}"; HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT"
for src in "$HERE"/tasks/t*_*; do
  name=$(basename "$src"); dst="$ROOT/$name"; rm -rf "$dst"; cp -r "$src" "$dst"; cd "$dst" || continue
  t0=$(date +%s.%N)
  timeout 900 claude -p "$(cat TASK.md)" --model "$MODEL" --permission-mode acceptEdits --output-format json --max-turns 25 > claude.json 2> claude.err; rc=$?
  t1=$(date +%s.%N)
  python3 - "$t0" "$t1" "$rc" <<'PY' > run.json
import sys, json
t0,t1,rc=sys.argv[1:]
d={}
try: d=json.load(open("claude.json"))
except Exception as e: d={"parse_error": str(e)[:100]}
u=d.get("usage",{}) or {}
json.dump({"wall_s": round(float(t1)-float(t0),1), "exit": int(rc), "num_turns": d.get("num_turns"), "is_error": d.get("is_error"),
           "terminal_reason": d.get("terminal_reason"), "input_tokens": u.get("input_tokens"), "cache_read": u.get("cache_read_input_tokens"),
           "output_tokens": u.get("output_tokens"), "models": list((d.get("modelUsage") or {}).keys()), "result_head": str(d.get("result"))[:100]}, sys.stdout)
PY
  echo "$name done rc=$rc"
done
python3 "$HERE/score.py" "$ROOT" "claude-$MODEL"
