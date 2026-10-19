"""Is the spread floor doing anything load-bearing, or is it an arbitrary knob?

The floor cannot be set a priori -- the engine's expected values are in heuristic units,
not game score, so there is no absolute "this decision is worth less than X" threshold to
appeal to. Picking a quantile makes the headline "N% of decisions are inconsequential"
circular: choose the 25th percentile and 25% fall below it by construction.

So the honest reporting is this sweep. If the agents' ordering and their ratios hold
across floors, the floor is not driving the conclusions and any reasonable choice is
defensible. If they move, the floor IS the result and must be justified separately.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import baselines  # noqa: E402
import metrics  # noqa: E402

pos = [json.loads(l) for l in open(os.path.join(HERE, "data", "oracle_rollout.jsonl"))]
ref = [json.loads(l) for l in open(os.path.join(HERE, "data", "reference_scores.jsonl"))]
d3 = [json.loads(l) for l in open(os.path.join(HERE, "data", "scores_d3_default.jsonl"))]
gids = [p["game"] for p in pos]
spreads = [metrics.spread(r["scores"]) for r in ref]

rng = random.Random(1234)
rand_moves = [baselines.legal_conditional_random(p["grid"], rng) for p in pos]
heur_moves = [baselines.heuristic_agent(p["grid"]) for p in pos]

print("raw spread distribution (heuristic units, NOT game score):")
vals = sorted(s for s in spreads if s is not None)
for q in (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.95):
    print("  p%-3d %14.1f" % (100 * q, vals[int(q * len(vals))]))

print("\n%-7s %12s %8s %10s %10s %10s %9s"
      % ("floor_q", "floor", "graded", "heuristic", "random", "d3_oracle", "h/r ratio"))
for q in (0.0, 0.05, 0.10, 0.25, 0.50):
    floor = metrics.choose_spread_floor(spreads, quantile=q) if q > 0 else 0.0
    h = metrics.clustered_mean_ci([metrics.normalized_regret(r["scores"], m, floor)
                                   for r, m in zip(ref, heur_moves)], gids)[0]
    rr = metrics.clustered_mean_ci([metrics.normalized_regret(r["scores"], m, floor)
                                    for r, m in zip(ref, rand_moves)], gids)[0]
    o = metrics.clustered_mean_ci([metrics.normalized_regret(a["scores"], b["best"], floor)
                                   for a, b in zip(ref, d3)], gids)[0]
    graded = sum(1 for s in spreads if s is not None and s >= floor)
    print("%-7.2f %12.1f %7.1f%% %10.4f %10.4f %10.4f %9.1fx"
          % (q, floor, 100.0 * graded / len(spreads), h, rr, o, rr / h if h else float("nan")))

print("\nIf the last column is stable, the floor is not driving the conclusions.")
