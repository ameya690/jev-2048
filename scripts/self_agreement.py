"""Step 1: how well does the oracle agree with itself? This is the CEILING.

No jev involved. If two reasonable expectimax configurations disagree on a position, no
agent can be expected to match the reference there, so jev's regret is read against this
number rather than against zero.

Two readings, and the second is the one that matters:

  AGREEMENT RATE -- how often two configs pick the same move. Legible but misleading:
  most 2048 positions have two near-equivalent moves, and counting those disagreements
  as errors punishes a config for a decision that costs nothing.

  CROSS-REGRET -- the alternative config's move scored under the REFERENCE config's value
  function, as normalised regret. Same scale as jev's regret, so it is what jev is
  compared to.

Everything is reported per game-stage stratum. Agreement is much easier on early boards
(the engine clamps search to distinctTiles-2, so configs collapse to the same shallow
search), and the stratum a search-free agent actually occupies is the one that counts.

Per-position scores are persisted so analysis can be rerun without recomputing, and the
reference config's scores double as the cache that run_arm1.py reads.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import metrics  # noqa: E402
import oracle  # noqa: E402
import strata  # noqa: E402

REFERENCE = "d5_default"
COMPARISONS = ["d3_default", "d5_altweights"]
DATA = os.path.join(HERE, "data")
POS_FILE = os.path.join(DATA, "oracle_rollout.jsonl")
OUT = os.path.join(HERE, "results", "self_agreement.json")


def score_file(name):
    # The reference config's scores are also Arm 1's cache; keep the filename it expects.
    return os.path.join(DATA, "reference_scores.jsonl" if name == REFERENCE else "scores_%s.jsonl" % name)


def score_all(name, positions):
    path = score_file(name)
    if os.path.exists(path):
        rows = [json.loads(l) for l in open(path)]
        if len(rows) == len(positions):
            print("%-16s cached (%d rows)" % (name, len(rows)), flush=True)
            return rows
    t0 = time.time()
    rows = []
    # Written to a temp file and renamed, so a partial file is never readable as a
    # complete cache. run_arm1.py reads the reference config's file by the same name.
    tmp = path + ".tmp"
    with oracle.Oracle.from_config(name) as orc, open(tmp, "w") as fh:
        for i, p in enumerate(positions):
            r = orc.analyze(p["grid"])
            row = {"best": r["best"], "scores": r["scores"], "depth": r["depth"]}
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            if i and i % 2500 == 0:
                print("  %s %d/%d (%.0fs)" % (name, i, len(positions), time.time() - t0), flush=True)
    os.replace(tmp, path)
    print("%-16s %d positions in %.0fs (%.1f ms/pos)"
          % (name, len(rows), time.time() - t0, 1000 * (time.time() - t0) / len(rows)), flush=True)
    return rows


positions = [json.loads(l) for l in open(POS_FILE)]
game_ids = [p["game"] for p in positions]
print("positions: %d from %d games\n" % (len(positions), len(set(game_ids))))

scored = {name: score_all(name, positions) for name in [REFERENCE] + COMPARISONS}

ref = scored[REFERENCE]
spreads = [metrics.spread(r["scores"]) for r in ref]
floor = metrics.choose_spread_floor(spreads, quantile=0.25)
n_decidable = sum(1 for s in spreads if s is not None)
gradeable = [s is not None and s >= floor for s in spreads]

print("\nspread floor (25th pct of non-degenerate spreads): %.6g" % floor)
print("  <2 legal moves (no decision)  : %5d (%4.1f%%)"
      % (len(spreads) - n_decidable, 100.0 * (len(spreads) - n_decidable) / len(spreads)))
print("  inconsequential (below floor) : %5d (%4.1f%%)"
      % (n_decidable - sum(gradeable), 100.0 * (n_decidable - sum(gradeable)) / len(spreads)))
print("  gradeable                     : %5d (%4.1f%%)"
      % (sum(gradeable), 100.0 * sum(gradeable) / len(spreads)))

report = {
    "n_positions": len(positions), "n_games": len(set(game_ids)), "spread_floor": floor,
    "frac_under_2_legal": (len(spreads) - n_decidable) / len(spreads),
    "frac_inconsequential": (n_decidable - sum(gradeable)) / len(spreads),
    "reference": REFERENCE, "overall": {}, "strata": {},
}

print("\n=== CEILING, overall ===  (cross-regret is spread-weighted, floor-free)")
print("%-16s %10s %10s  %-28s" % ("config", "agree_all", "agree_grd", "cross-regret vs " + REFERENCE))
cross_moves = {}
for name in COMPARISONS:
    alt = scored[name]
    cross_moves[name] = [b["best"] for b in alt]
    agree_all = sum(1 for a, b in zip(ref, alt) if a["best"] == b["best"]) / len(ref)
    gr = [(a, b) for a, b, g in zip(ref, alt, gradeable) if g]
    agree_grd = sum(1 for a, b in gr if a["best"] == b["best"]) / max(1, len(gr))
    m, lo, hi, ng = metrics.spread_weighted_regret(ref, cross_moves[name], game_ids)
    print("%-16s %9.1f%% %9.1f%%  %.4f [%.4f, %.4f] n=%d" % (name, 100 * agree_all, 100 * agree_grd, m, lo, hi, ng))
    report["overall"][name] = {"agreement_all": agree_all, "agreement_gradeable": agree_grd,
                               "cross_regret": m, "lo": lo, "hi": hi, "n_games": ng}

print("\n=== CEILING, by game stage ===")
print("%-10s %7s %8s  %-22s %-22s" % ("stratum", "n", "gradbl", "d3_default", "d5_altweights"))
groups = strata.group(positions)
for _, _, label in strata.STRATA:
    ii = groups[label]
    if not ii:
        continue
    g = [game_ids[i] for i in ii]
    frac_gr = sum(1 for i in ii if gradeable[i]) / len(ii)
    cells, entry = [], {"n": len(ii), "frac_gradeable": frac_gr}
    sub_ref = [ref[i] for i in ii]
    for name in COMPARISONS:
        m, lo, hi, ng = metrics.spread_weighted_regret(sub_ref, [cross_moves[name][i] for i in ii], g)
        cells.append("%.4f [%.3f,%.3f]" % (m, lo, hi))
        entry[name] = {"cross_regret": m, "lo": lo, "hi": hi, "n_games": ng}
    mark = "  <- live regime" if label in strata.LIVE else ""
    print("%-10s %7d %7.1f%%  %-22s %-22s%s" % (label, len(ii), 100 * frac_gr, cells[0], cells[1], mark))
    report["strata"][label] = entry

with open(OUT, "w") as fh:
    json.dump(report, fh, indent=2)
print("\nwrote %s" % OUT)
print("CEILING: jev's regret is read against the cross-regret columns, not against 0.")
print("The rows marked 'live regime' are the ones a search-free agent actually occupies.")
