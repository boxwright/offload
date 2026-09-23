#!/bin/bash
# Maintenance-window test: prove install/compose.yaml (upstream llama.cpp image + proxy) on this GPU with the model
# named in $W/stack.env, measure it, calibrate it, and run one real job through it.
# Usage: window_test.sh up | measure | calibrate <label> | job | down
# Run `up` only after the box's usual model server and its proxy are stopped (the proxy container name is shared).
set -uo pipefail
W=$HOME/.local/share/offload/window; SRC=$HOME/.local/share/offload/src
DC="docker compose --env-file $W/stack.env -f $SRC/install/compose.yaml"
PORT=$(grep -oP '^OFFLOAD_MODEL_PORT=\K.*' "$W/stack.env" 2>/dev/null || echo 8080)
case "${1:-}" in
  up)
    t0=$(date +%s); $DC up -d --build 2>&1 | tail -3
    for i in $(seq 1 120); do curl -fs "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 2; done
    curl -fs "http://127.0.0.1:$PORT/health" && echo "  model ready after $(( $(date +%s) - t0 )) s" \
      || { echo "MODEL DID NOT COME UP"; docker logs offload-model 2>&1 | tail -25; exit 1; }
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader ;;
  measure)
    echo "--- stack.env:"; cat "$W/stack.env"
    echo "--- GPU memory:"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
    for kind in prose code; do
      if [ $kind = prose ]; then ask="Write 300 words of plain prose about maintaining a home server. No lists."
      else ask="Write a Python module with a class LRUCache(capacity) with get and put methods and a short test. Code only."; fi
      echo "--- decode speed ($kind, 400 tokens):"
      curl -s -m 300 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'content-type: application/json' \
        -d "{\"model\":\"m\",\"max_tokens\":400,\"temperature\":0,\"messages\":[{\"role\":\"user\",\"content\":\"$ask\"}]}" \
        | python3 -c "import json,sys; t=json.load(sys.stdin).get('timings',{}); print({k: round(t.get(k,0),1) for k in ('prompt_per_second','predicted_per_second','predicted_n')}, 'draft:', {k:t.get(k) for k in t if 'draft' in k})"
    done
    echo "--- a tool task through sandbox -> proxy -> model:"
    rm -rf /tmp/window-harness && mkdir -p /tmp/window-harness
    t0=$(date +%s.%N)
    docker run --rm --network offload_net --cap-add=NET_ADMIN --cap-add=NET_RAW -e ANTHROPIC_BASE_URL=http://offload-proxy:4000 \
      -e ANTHROPIC_AUTH_TOKEN=local -e ANTHROPIC_MODEL=local-model -e ANTHROPIC_SMALL_FAST_MODEL=local-model \
      -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 -e OFFLOAD_ALLOW_HOSTS= -v /tmp/window-harness:/workspace offload-sandbox:latest \
      'claude -p "Create hello.txt containing exactly: hello from the default install. Then read it back and reply with its contents." --model local-model --permission-mode dontAsk --allowedTools "Read,Write,Edit,Bash(cat *)" --output-format json --max-turns 8 < /dev/null' \
      | python3 -c "import json,sys; d=json.loads(sys.stdin.read().strip().splitlines()[-1]); print({k:d.get(k) for k in ('is_error','num_turns','duration_ms')}, '|', str(d.get('result'))[:80])"
    echo "  wall $(python3 -c "print(round($(date +%s.%N)-$t0,1))") s"; cat /tmp/window-harness/hello.txt 2>&1 ;;
  calibrate)
    label="${2:?label}"; out="$W/calibration-$label"; rm -rf "$out"
    bash "$SRC/calibration/run_harness.sh" "$out" offload_net http://offload-proxy:4000 "$label" | tee "$W/results-$label.jsonl" ;;
  job)
    # One real job on the window stack, run in the foreground with a config that points at offload_net.
    mkdir -p "$W/jobs"
    sed -e 's/^docker_network:.*//' -e 's/^proxy_url:.*//' -e 's/^jobs_root:.*//' ~/.config/offload/config.yaml > "$W/config.yaml"
    printf 'docker_network: offload_net\nproxy_url: http://offload-proxy:4000\njobs_root: %s/jobs\n' "$W" >> "$W/config.yaml"
    n=1; while [ -e "$W/jobs/window-$(printf %03d $n)" ]; do n=$((n+1)); done; id="window-$(printf %03d $n)"
    mkdir -p "$W/jobs/$id"; sed "s/demo-006/$id/g" ~/.local/share/offload/jobs/demo-006/job.md > "$W/jobs/$id/job.md"
    OFFLOAD_CONFIG="$W/config.yaml" offload run "$W/jobs/$id"; echo "exit=$?"
    OFFLOAD_CONFIG="$W/config.yaml" offload report "$W/jobs/$id" 2>/dev/null | head -12 ;;
  down) $DC down 2>&1 | tail -2; nvidia-smi --query-gpu=memory.used --format=csv,noheader ;;
  *) echo "usage: $0 up|measure|calibrate <label>|job|down"; exit 2 ;;
esac
