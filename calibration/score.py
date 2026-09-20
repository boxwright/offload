#!/usr/bin/env python3
"""score.py <work_root> <worker_label> — run pytest in each task dir under work_root, verify tests unchanged, print one JSON line per task."""
import sys, os, json, hashlib, subprocess, time, glob
root, label = sys.argv[1], sys.argv[2]
here = os.path.dirname(os.path.abspath(__file__))
sums = json.load(open(os.path.join(here, "tests.sha256.json")))
for d in sorted(glob.glob(os.path.join(root, "t*_*"))):
    name = os.path.basename(d)
    tampered = [k for k in sums if k.startswith(name + "/") and
                (not os.path.exists(os.path.join(root, k)) or hashlib.sha256(open(os.path.join(root, k), "rb").read()).hexdigest() != sums[k])]
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider"], cwd=d, capture_output=True, text=True, timeout=300)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    meta = {}
    mp = os.path.join(d, "run.json")
    if os.path.exists(mp):
        try: meta = json.load(open(mp))
        except Exception: pass
    print(json.dumps({"worker": label, "task": name, "pass": r.returncode == 0 and not tampered, "pytest": last[:120],
                      "tests_tampered": tampered, **meta}))
