"""How are oracle-rollout positions distributed across game stages?

This decides whether the agreed Q9 headline -- the gap between oracle-rollout and
jev-rollout regret -- is interpretable as written. A depth-3 oracle reaches 4096-8192;
a no-search agent will not get near that. If the two rollouts occupy disjoint board
regimes, the "gap" conflates two different things: jev's errors compounding, and jev
being scored on entirely different positions. Stratifying by max tile is the fix.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POS = os.path.join(HERE, "data", "oracle_rollout.jsonl")
rows = [json.loads(l) for l in open(POS)]

by_tile = Counter(r["max_tile"] for r in rows)
n = len(rows)
print("%d sampled positions from %d games\n" % (n, len({r["game"] for r in rows})))
print("%-10s %8s %8s %10s" % ("max tile", "count", "share", "cumulative"))
cum = 0
for t in sorted(by_tile):
    cum += by_tile[t]
    print("%-10d %8d %7.1f%% %9.1f%%" % (t, by_tile[t], 100.0 * by_tile[t] / n, 100.0 * cum / n))

reach = {}
for thresh in (256, 512, 1024, 2048):
    share = sum(c for t, c in by_tile.items() if t <= thresh) / n
    reach[thresh] = share
print("\nShare of oracle-rollout positions a no-search agent plausibly reaches:")
for t, s in reach.items():
    print("  boards with max tile <= %5d : %5.1f%%" % (t, 100 * s))

legal = Counter(r["n_legal"] for r in rows)
print("\nLegal-move count (sets the legal-conditional random baseline, NOT 25%%):")
exp_rand = 0.0
for k in sorted(legal):
    print("  %d legal: %6d (%4.1f%%)  random agreement = %.0f%%"
          % (k, legal[k], 100.0 * legal[k] / n, 100.0 / k if k else 0))
    if k:
        exp_rand += (legal[k] / n) * (1.0 / k)
print("  -> expected random top-1 agreement over this set: %.1f%%" % (100 * exp_rand))
