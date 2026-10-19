"""Re-run the headline with the PROSE encoding, which the ablation showed is worth ~half
of jev's measured regret. Reporting the raw-grid number as the result would understate
jev purely because of a formatting choice I made in the design phase.

Also re-measures the illegal-move rate under prose: if the raw grid was the reason jev
could not tell which moves were legal, prose should fix that too. If it does not, the
legality blindness is about the model rather than the encoding.
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
import baselines  # noqa: E402
import board  # noqa: E402
import jev_client  # noqa: E402
import metrics  # noqa: E402
import strata  # noqa: E402

ROWNAMES = ["top", "second", "third", "bottom"]


def prose(grid):
    out = []
    for r in range(4):
        cells = ["%d" % (1 << v) if v else "empty" for v in grid[r * 4:r * 4 + 4]]
        out.append("The %s row, left to right, is %s." % (ROWNAMES[r], ", ".join(cells)))
    return " ".join(out)


MODE = sys.argv[1] if len(sys.argv) > 1 else "masked"
MAX_WORKERS = 6
pos = [json.loads(l) for l in open(os.path.join(HERE, "data", "oracle_rollout.jsonl"))]
ref = [json.loads(l) for l in open(os.path.join(HERE, "data", "reference_scores.jsonl"))]

if MODE == "unmasked":
    groups = strata.group(pos)
    sample = []
    for _, _, nm in strata.STRATA:
        ii = groups[nm]
        step = max(1, len(ii) // 400)
        sample += ii[::step][:400]
    RAW = os.path.join(HERE, "data", "prose_unmasked_raw.jsonl")
else:
    sample = list(range(len(pos)))
    RAW = os.path.join(HERE, "data", "prose_masked_raw.jsonl")

key = jev_client.load_key()
url, model = jev_client.endpoint_for(key)
done = {}
if os.path.exists(RAW):
    for line in open(RAW):
        r = json.loads(line)
        done[r["i"]] = r
print("mode=%s  sample=%d  cached=%d" % (MODE, len(sample), len(done)), flush=True)

lock = threading.Lock()
spent = sum(r.get("cost") or 0 for r in done.values())
t0 = time.time()
with open(RAW, "a") as fh:
    def ask(i):
        global spent
        grid = pos[i]["grid"]
        body, dirs = jev_client.build_request(grid, model, mask_illegal=(MODE == "masked"))
        body["state"] = jev_client.RULES + "\n\n" + prose(grid)
        if not dirs:
            return
        try:
            payload = jev_client.post(url, key, body)
        except Exception:
            return
        d, probs, conf, cost = jev_client.parse_response(payload)
        rec = {"i": i, "choice": d, "probs": {str(k): v for k, v in probs.items()},
               "confidence": conf, "cost": cost}
        with lock:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[i] = rec
            spent += cost or 0.0
            if len(done) % 1000 == 0:
                print("  %d/%d  $%.4f" % (len(done), len(sample), spent), flush=True)

    todo = [i for i in sample if i not in done]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(ask, todo))
print("%.0fs  $%.4f\n" % (time.time() - t0, spent), flush=True)

if MODE == "unmasked":
    n = bad = 0
    byn = defaultdict(lambda: [0, 0])
    for i in sample:
        if i not in done:
            continue
        legal = set(board.legal_moves(pos[i]["grid"]))
        n += 1
        ill = done[i]["choice"] not in legal
        bad += 1 if ill else 0
        b = byn[len(legal)]
        b[0] += 1
        b[1] += 1 if ill else 0
    print("ILLEGAL-MOVE RATE under PROSE: %d/%d = %.2f%%" % (bad, n, 100.0 * bad / max(1, n)))
    for k in sorted(byn):
        c, e = byn[k]
        print("  %d legal: %5d positions, %5.2f%% illegal (chance %.0f%%)"
              % (k, c, 100.0 * e / c, 100.0 * (4 - k) / 4))
    sys.exit(0)

gids = [pos[i]["game"] for i in sample]
sub_ref = [ref[i] for i in sample]
jev_moves = [done.get(i, {}).get("choice", -1) for i in sample]
import random  # noqa: E402
rng = random.Random(1234)
rand_moves = [baselines.legal_conditional_random(pos[i]["grid"], rng) for i in sample]
heur_moves = [baselines.heuristic_agent(pos[i]["grid"]) for i in sample]
grid_moves = []
gridraw = {}
for line in open(os.path.join(HERE, "data", "jev_arm1_raw.jsonl")):
    r = json.loads(line)
    gridraw[r["i"]] = r
grid_moves = [gridraw.get(i, {}).get("choice", -1) for i in sample]

print("%-26s %9s  %-24s" % ("agent", "regret", "95% CI (clustered by game)"))
for nm, mv in (("jev (prose)", jev_moves), ("jev (raw grid)", grid_moves),
               ("hand heuristic", heur_moves), ("legal-conditional random", rand_moves)):
    m, lo, hi, ng = metrics.spread_weighted_regret(sub_ref, mv, gids)
    print("%-26s %9.4f  [%.4f, %.4f] n=%d" % (nm, m, lo, hi, ng))

print()
for a, b, la, lb in ((jev_moves, grid_moves, "prose", "raw grid"),
                     (jev_moves, heur_moves, "prose", "heuristic"),
                     (jev_moves, rand_moves, "prose", "random")):
    dm, dlo, dhi, _ = metrics.paired_spread_weighted(sub_ref, a, b, gids)
    tag = "%s better" % la if dhi < 0 else ("%s better" % lb if dlo > 0 else "indistinguishable")
    print("  paired %-6s - %-10s: %+.4f [%+.4f, %+.4f] -> %s" % (la, lb, dm, dlo, dhi, tag))

rnd = metrics.spread_weighted_regret(sub_ref, rand_moves, gids)[0]
print("\n  share of the random->oracle gap recovered:")
for nm, mv in (("jev (prose)", jev_moves), ("jev (raw grid)", grid_moves), ("hand heuristic", heur_moves)):
    m = metrics.spread_weighted_regret(sub_ref, mv, gids)[0]
    print("    %-16s %.1f%%" % (nm, 100.0 * (rnd - m) / rnd))
