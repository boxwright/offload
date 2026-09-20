#!/bin/bash
# Maintenance-window test: prove install/compose.yaml (upstream llama.cpp image + proxy) on this GPU.
# Usage: window_test.sh up | measure | down      Run `up` only after the box's usual model server is stopped.
set -uo pipefail
W=$HOME/.local/share/offload/window; SRC=$HOME/.local/share/offload/src
DC="docker compose --env-file $W/stack.env -f $SRC/install/compose.yaml"
case "${1:-}" in
  up)
    t0=$(date +%s); $DC up -d --build 2>&1 | tail -3
    for i in $(seq 1 90); do curl -fs http://127.0.0.1:8081/health >/dev/null 2>&1 && break; sleep 2; done
    curl -fs http://127.0.0.1:8081/health && echo "  model ready after $(( $(date +%s) - t0 )) s" || { echo "MODEL DID NOT COME UP"; docker logs offload-model 2>&1 | tail -25; exit 1; }
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader ;;
  measure)
    echo "--- decode speed (400 tokens of prose), spec decoding per stack.env: $(grep SPEC $W/stack.env)"
    curl -s -m 300 http://127.0.0.1:8081/v1/chat/completions -H 'content-type: application/json' -d '{"model":"m","max_tokens":400,"temperature":0,"messages":[{"role":"user","content":"Write 300 words of plain prose about maintaining a home server. No lists."}]}' \
      | python3 -c "import json,sys; t=json.load(sys.stdin).get('timings',{}); print({k: round(t.get(k,0),1) for k in ('prompt_per_second','predicted_per_second','predicted_n')}, 'draft:', {k:t.get(k) for k in t if 'draft' in k})"
    echo "--- the sandbox reaches the proxy on offload_net, and the harness drives the model"
    rm -rf /tmp/window-harness && mkdir -p /tmp/window-harness
    docker run --rm --network offload_net --cap-add=NET_ADMIN --cap-add=NET_RAW -e ANTHROPIC_BASE_URL=http://offload-proxy:4000 -e ANTHROPIC_AUTH_TOKEN=local \
      -e ANTHROPIC_MODEL=local-model -e ANTHROPIC_SMALL_FAST_MODEL=local-model -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 -v /tmp/window-harness:/workspace offload-sandbox:latest bash -c '
      export PATH=/usr/local/share/npm-global/bin:$PATH; sudo /usr/local/bin/init-firewall.sh >/dev/null 2>&1 || { echo FIREWALL FAILED; exit 97; }; cd /workspace
      claude -p "Create hello.txt containing exactly: hello from the default install. Then read it back and reply with its contents." --model local-model --permission-mode dontAsk --allowedTools "Read,Write,Edit,Bash(cat *)" --output-format json --max-turns 8 < /dev/null' \
      | python3 -c "import json,sys; d=json.loads(sys.stdin.read().strip().splitlines()[-1]); print({k:d.get(k) for k in ('is_error','num_turns','duration_ms')}, '|', str(d.get('result'))[:80])"
    cat /tmp/window-harness/hello.txt 2>&1 ;;
  down) $DC down 2>&1 | tail -2; nvidia-smi --query-gpu=memory.used --format=csv,noheader ;;
  *) echo "usage: $0 up|measure|down"; exit 2 ;;
esac
