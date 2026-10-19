"""Score every rollout position with ONE oracle config, into that config's cache file.

Exists so the slow depth-5 configs can run in parallel processes instead of sequentially
inside self_agreement.py, which picks the caches up and skips the work. Writes via a temp
file and os.replace, so a partial run is never visible as a complete cache -- the worst
case is that the consumer recomputes, never that it reads truncated data.

    python3 scripts/score_config.py d5_altweights
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import oracle  # noqa: E402

REFERENCE = "d5_default"
name = sys.argv[1]
positions = [json.loads(l) for l in open(os.path.join(HERE, "data", "oracle_rollout.jsonl"))]
path = os.path.join(HERE, "data",
                    "reference_scores.jsonl" if name == REFERENCE else "scores_%s.jsonl" % name)

if os.path.exists(path) and len(open(path).readlines()) == len(positions):
    print("%s already cached" % name)
    sys.exit(0)

t0 = time.time()
tmp = path + ".tmp"
with oracle.Oracle.from_config(name) as orc, open(tmp, "w") as fh:
    for i, p in enumerate(positions):
        r = orc.analyze(p["grid"])
        fh.write(json.dumps({"best": r["best"], "scores": r["scores"], "depth": r["depth"]}) + "\n")
        if i and i % 1000 == 0:
            print("  %s %d/%d (%.0fs)" % (name, i, len(positions), time.time() - t0), flush=True)
os.replace(tmp, path)
print("%s: %d positions in %.0fs (%.1f ms/pos) -> %s"
      % (name, len(positions), time.time() - t0, 1000 * (time.time() - t0) / len(positions), path), flush=True)
