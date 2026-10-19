"""Q10's second metric: how often does jev pick an ILLEGAL move when offered all four?

Separate from move quality on purpose. The masked runs never offer an illegal direction,
which is what any real deployment would do and is the right basis for scoring judgment.
But "does jev understand the mechanics of the state it was given" is a different question,
and folding it into the quality number would conflate not grasping the board with picking
a weak move. It is also a pointed question for a model whose pitch is that it cannot
produce invalid output -- type-validity is not game-legality.

Subsampled, because this is a proportion rather than a mean over a heavy-tailed quantity:
a few thousand positions pin it down tightly, and there is no reason to pay for 9,193.
Stratified across game stages so a board-fullness effect would be visible.
"""
import json
import os
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402
import jev_client  # noqa: E402
import strata  # noqa: E402

MAX_WORKERS = 6
PER_STRATUM = int(sys.argv[1]) if len(sys.argv) > 1 else 400
POS_FILE = os.path.join(HERE, "data", "oracle_rollout.jsonl")
OUT_RAW = os.path.join(HERE, "data", "jev_unmasked_raw.jsonl")

positions = [json.loads(l) for l in open(POS_FILE)]
groups = strata.group(positions)
sample = []
for _, _, name in strata.STRATA:
    ii = groups[name]
    if not ii:
        continue
    step = max(1, len(ii) // PER_STRATUM)
    sample += [(i, name) for i in ii[::step][:PER_STRATUM]]
print("sampling %d positions across %d strata" % (len(sample), len(groups)), flush=True)

done = {}
if os.path.exists(OUT_RAW):
    for line in open(OUT_RAW):
        try:
            r = json.loads(line)
            done[r["i"]] = r
        except Exception:
            pass
    print("resuming: %d already answered" % len(done), flush=True)

key = jev_client.load_key()
url, model = jev_client.endpoint_for(key)
todo = [(i, n) for i, n in sample if i not in done]
lock = threading.Lock()
t0 = time.time()
spent = sum(r.get("cost") or 0 for r in done.values())

with open(OUT_RAW, "a") as fh:
    def ask(item):
        global spent
        i, name = item
        grid = positions[i]["grid"]
        legal = set(board.legal_moves(grid))
        try:
            d, probs, conf, cost, _ = jev_client.query_move(
                key, url, model, grid, mask_illegal=False)
        except Exception:
            return
        rec = {"i": i, "stratum": name, "choice": d, "legal": sorted(legal),
               "was_legal": d in legal, "n_legal": len(legal),
               "illegal_mass": round(sum(v for k2, v in probs.items() if k2 not in legal), 4),
               "confidence": conf, "cost": cost}
        with lock:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[i] = rec
            spent += cost or 0.0
            if len(done) % 250 == 0:
                print("  %d/%d  $%.4f" % (len(done), len(sample), spent), flush=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(ask, todo))

rows = [done[i] for i, _ in sample if i in done]
print("\n%d answered in %.0fs, $%.4f\n" % (len(rows), time.time() - t0, spent))

n_ill = sum(1 for r in rows if not r["was_legal"])
print("ILLEGAL-MOVE RATE (all four directions offered)")
print("  overall: %d/%d = %.2f%%" % (n_ill, len(rows), 100.0 * n_ill / max(1, len(rows))))
mass = sum(r["illegal_mass"] for r in rows) / max(1, len(rows))
print("  mean probability mass jev placed on illegal moves: %.4f" % mass)

by = defaultdict(lambda: [0, 0, 0.0])
for r in rows:
    b = by[r["stratum"]]
    b[0] += 1
    b[1] += 0 if r["was_legal"] else 1
    b[2] += r["illegal_mass"]
print("\n  %-10s %7s %10s %14s" % ("stratum", "n", "illegal%", "illegal mass"))
for _, _, name in strata.STRATA:
    if name not in by:
        continue
    n, bad, m = by[name]
    mark = "  <- live regime" if name in strata.LIVE else ""
    print("  %-10s %7d %9.2f%% %14.4f%s" % (name, n, 100.0 * bad / n, m / n, mark))

byn = defaultdict(lambda: [0, 0])
for r in rows:
    b = byn[r["n_legal"]]
    b[0] += 1
    b[1] += 0 if r["was_legal"] else 1
print("\n  by number of legal moves (4 legal = impossible to err):")
for k in sorted(byn):
    n, bad = byn[k]
    print("    %d legal: %5d positions, %5.2f%% illegal" % (k, n, 100.0 * bad / n))

with open(os.path.join(HERE, "results", "illegal_rate.json"), "w") as fh:
    json.dump({"n": len(rows), "illegal_rate": n_ill / max(1, len(rows)),
               "mean_illegal_mass": mass,
               "by_stratum": {k: {"n": v[0], "illegal": v[1], "mass": v[2] / v[0]} for k, v in by.items()}},
              fh, indent=2)
print("\nwrote results/illegal_rate.json")
