"""Query jev for every rollout position, appending raw responses to the shared cache.

Split out from run_arm1.py so the API calls (~8 min) can overlap the oracle scoring
(~10 min) instead of queueing behind it. run_arm1.py reads the same file and will find
the work done. Resumable: already-answered indices are skipped, so a stall or a kill
costs nothing but the in-flight calls.
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import jev_client  # noqa: E402

MAX_WORKERS = 6
POS_FILE = os.path.join(HERE, "data", "oracle_rollout.jsonl")
RAW_FILE = os.path.join(HERE, "data", "jev_arm1_raw.jsonl")

positions = [json.loads(l) for l in open(POS_FILE)]
key = jev_client.load_key()
url, model = jev_client.endpoint_for(key)
print("endpoint %s  model %s  positions %d" % (url, model, len(positions)), flush=True)

done = set()
spent = 0.0
if os.path.exists(RAW_FILE):
    for line in open(RAW_FILE):
        try:
            r = json.loads(line)
            done.add(r["i"])
            spent += r.get("cost") or 0.0
        except Exception:
            pass
print("already answered: %d" % len(done), flush=True)

todo = [i for i in range(len(positions)) if i not in done]
lock = threading.Lock()
t0 = time.time()
errors = []

with open(RAW_FILE, "a") as fh:
    def ask(i):
        global spent
        try:
            d, probs, conf, cost, _ = jev_client.query_move(key, url, model, positions[i]["grid"])
        except Exception as e:
            with lock:
                errors.append((i, repr(e)[:160]))
            return
        rec = {"i": i, "choice": d, "probs": {str(k): v for k, v in probs.items()},
               "confidence": conf, "cost": cost}
        with lock:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done.add(i)
            spent += cost or 0.0
            n = len(done)
            if n % 1000 == 0:
                el = time.time() - t0
                print("  %d/%d  %.1f/s  $%.4f  errors %d"
                      % (n, len(positions), (n - (len(positions) - len(todo))) / max(el, 1e-9), spent, len(errors)),
                      flush=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(ask, todo))

print("done: %d/%d answered in %.0fs, $%.4f, %d errors"
      % (len(done), len(positions), time.time() - t0, spent, len(errors)), flush=True)
for i, e in errors[:10]:
    print("  error at %d: %s" % (i, e))
