#!/usr/bin/env python3
"""Measure prefill, decode and cached-prefix follow-up latency on an OpenAI-compatible llama-server / mlx_lm endpoint.
Usage: llm_bench.py <base_url> <model> <prefix_tokens_target> [effort]
Turn 1: cold prompt of ~N tokens. Turn 2/3: same prefix + a short new question. Then a 400-token decode run.
Prints JSON lines with wall seconds and server timings when available."""
import json, sys, time, urllib.request, os, glob
base, model, target = sys.argv[1], sys.argv[2], int(sys.argv[3])
effort = sys.argv[4] if len(sys.argv) > 4 else "medium"
# Build a deterministic prefix from real markdown (Hub notes) so the test is on real material.
pf = os.environ.get("PREFIX_FILE"); text = open(pf).read()[: int(target * 3.6)]
sysmsg = "You are a careful assistant. Answer in one short sentence."
def call(messages, max_tokens):
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0,
            "chat_template_kwargs": {"reasoning_effort": effort}}
    req = urllib.request.Request(base + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time(); r = json.load(urllib.request.urlopen(req, timeout=1800)); wall = time.time() - t0
    out = {"wall_s": round(wall, 2), "usage": r.get("usage"), "timings": r.get("timings")}
    out["answer"] = (r["choices"][0]["message"].get("content") or "")[:80]
    return out
prefix = [{"role": "system", "content": sysmsg}, {"role": "user", "content": "Reference material:\n" + text + "\n\nQuestion: what box is described first? One sentence."}]
res = {"base": base, "model": model, "effort": effort}
res["turn1_cold"] = call(prefix, 48)
conv = prefix + [{"role": "assistant", "content": res["turn1_cold"]["answer"]}, {"role": "user", "content": "Name one more box in one sentence."}]
res["turn2_cached"] = call(conv, 48)
conv = conv + [{"role": "assistant", "content": res["turn2_cached"]["answer"]}, {"role": "user", "content": "And a third, one sentence."}]
res["turn3_cached"] = call(conv, 48)
res["decode_400"] = call([{"role": "system", "content": sysmsg}, {"role": "user", "content": "Write 400 words of plain prose about maintaining a home server. No lists."}], 400)
print(json.dumps(res, indent=1))
