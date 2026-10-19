"""Does the board ENCODING explain jev's weakness? Three encodings, same positions.

The review proposed describing the board in words, e.g. "largest tile 256 in the
bottom-left corner, 3 empty cells, bottom row ordered". That is worth testing, but as
written it leaks: empty-cell count, max-tile-in-corner and row monotonicity are three of
the four terms in the hand heuristic jev is being compared against. If performance jumps,
the finding would be "jev can read features I computed", not "jev reads prose better".

So both are run, on identical positions (paired):

  grid      raw 4x4 of tile values                       -- what Arm 1 used
  prose     the same information in sentences, NO derived features
  features  prose PLUS the leaky summary the review suggested

prose vs grid isolates representation. features vs prose prices the leak. If features is
the only one that helps, the weakness is not the encoding.
"""
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402
import jev_client  # noqa: E402
import metrics  # noqa: E402
import strata  # noqa: E402

PER_STRATUM = int(sys.argv[1]) if len(sys.argv) > 1 else 200
MAX_WORKERS = 6
ROWNAMES = ["top", "second", "third", "bottom"]
COLNAMES = ["leftmost", "second", "third", "rightmost"]
CORNERS = {0: "top-left", 3: "top-right", 12: "bottom-left", 15: "bottom-right"}


def prose(grid):
    out = []
    for r in range(4):
        cells = []
        for c in range(4):
            v = grid[r * 4 + c]
            cells.append("%d" % (1 << v) if v else "empty")
        out.append("The %s row, left to right, is %s." % (ROWNAMES[r], ", ".join(cells)))
    return " ".join(out)


def features(grid):
    """Deliberately leaky: these are the hand heuristic's own inputs."""
    mx = max(range(16), key=lambda i: grid[i])
    where = CORNERS.get(mx, "the %s row, %s column" % (ROWNAMES[mx // 4], COLNAMES[mx % 4]))
    empty = sum(1 for v in grid if v == 0)
    ordered = []
    for r in range(4):
        row = [grid[r * 4 + c] for c in range(4)]
        nz = [x for x in row if x]
        if len(nz) > 1 and (nz == sorted(nz) or nz == sorted(nz, reverse=True)):
            ordered.append(ROWNAMES[r])
    s = "The largest tile is %d, at %s. There are %d empty cells." % (1 << grid[mx], where, empty)
    if ordered:
        s += " These rows are in order: %s." % ", ".join(ordered)
    return prose(grid) + " " + s


ENCODERS = {"grid": None, "prose": prose, "features": features}

pos = [json.loads(l) for l in open(os.path.join(HERE, "data", "oracle_rollout.jsonl"))]
ref = [json.loads(l) for l in open(os.path.join(HERE, "data", "reference_scores.jsonl"))]
groups = strata.group(pos)
sample = []
for _, _, name in strata.STRATA:
    ii = groups[name]
    step = max(1, len(ii) // PER_STRATUM)
    sample += ii[::step][:PER_STRATUM]
print("paired sample: %d positions across %d strata\n" % (len(sample), len(groups)), flush=True)

key = jev_client.load_key()
url, model = jev_client.endpoint_for(key)
RAW = os.path.join(HERE, "data", "encoding_ablation_raw.jsonl")
done = {}
if os.path.exists(RAW):
    for line in open(RAW):
        r = json.loads(line)
        done[(r["enc"], r["i"])] = r

lock = threading.Lock()
spent = sum(r.get("cost") or 0 for r in done.values())
t0 = time.time()
with open(RAW, "a") as fh:
    def ask(item):
        global spent
        enc, i = item
        grid = pos[i]["grid"]
        fn = ENCODERS[enc]
        body, dirs = jev_client.build_request(grid, model)
        if fn is not None:
            body["state"] = jev_client.RULES + "\n\n" + fn(grid)
        if not dirs:
            return
        try:
            payload = jev_client.post(url, key, body)
        except Exception:
            return
        d, probs, conf, cost = jev_client.parse_response(payload)
        rec = {"enc": enc, "i": i, "choice": d, "cost": cost}
        with lock:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[(enc, i)] = rec
            spent += cost or 0.0

    todo = [(e, i) for e in ENCODERS for i in sample if (e, i) not in done]
    print("calls to make: %d (%d cached)" % (len(todo), len(done)), flush=True)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(ask, todo))

print("%.0fs, $%.4f\n" % (time.time() - t0, spent))

gids = [pos[i]["game"] for i in sample]
sub_ref = [ref[i] for i in sample]
print("%-10s %9s  %-24s" % ("encoding", "regret", "95% CI (clustered by game)"))
results = {}
for enc in ENCODERS:
    moves = [done.get((enc, i), {}).get("choice", -1) for i in sample]
    m, lo, hi, n = metrics.spread_weighted_regret(sub_ref, moves, gids)
    results[enc] = moves
    print("%-10s %9.4f  [%.4f, %.4f] n=%d" % (enc, m, lo, hi, n))

print()
for a, b in (("prose", "grid"), ("features", "prose"), ("features", "grid")):
    dm, dlo, dhi, _ = metrics.paired_spread_weighted(sub_ref, results[a], results[b], gids)
    tag = "%s better" % a if dhi < 0 else ("%s better" % b if dlo > 0 else "indistinguishable")
    print("  paired %-9s - %-9s: %+.4f [%+.4f, %+.4f]  -> %s" % (a, b, dm, dlo, dhi, tag))
