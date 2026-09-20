#!/usr/bin/env python3
"""Capture a real `offload demo` session: each command, its output, and when it ran. Writes docs/assets/demo-transcript.json."""
import json, re, subprocess, time
def run(cmd):
    t = time.time(); out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120).stdout.rstrip()
    return {"at": round(t - T0, 1), "cmd": cmd, "out": out}
T0 = time.time(); frames = [run("offload demo")]
job = re.search(r"queued (\S+)\.", frames[0]["out"]).group(1)
while True:
    time.sleep(9)
    f = run("offload status"); f["out"] = "\n".join(l for l in f["out"].splitlines() if l.startswith(job)); frames.append(f)
    if re.search(r"\s(done|failed)\s", f["out"]) or time.time() - T0 > 900: break
frames.append(run(f"offload report {job}")); frames.append(run("offload cost | head -1"))
json.dump({"job": job, "captured": time.strftime("%Y-%m-%d %H:%M"), "frames": frames}, open("docs/assets/demo-transcript.json", "w"), indent=1)
print("captured", job, len(frames), "frames", round(time.time() - T0), "s")
