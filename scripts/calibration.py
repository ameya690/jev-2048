"""Are jev's probabilities calibrated against ground truth?

This is the question 2048 is actually a good instrument for. Calibration claims are
normally unfalsifiable in deployment -- there is no oracle to check against. Here there
is: expectimax computes the true value of every move, so "jev said 0.7" can be checked
against "was it in fact the best move 70% of the time".

Costs no extra calls: run_arm1/warm_jev persist the full distribution per position.

RELIABILITY. Bin every (move, stated probability) pair by the probability. In each bin,
measure how often that move really was the oracle's best. A calibrated model sits on the
diagonal. ECE is the bin-size-weighted mean gap from it.

BRIER. Multi-class Brier score against the indicator of the oracle's best move; lower is
better. Compared against two references: a uniform-over-legal predictor, and jev's own
distribution with its ranking kept but confidence flattened. The second isolates whether
the MAGNITUDES carry information or only the ordering does -- which is the whole claim.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import metrics  # noqa: E402
import strata  # noqa: E402

POS = os.path.join(HERE, "data", "oracle_rollout.jsonl")
REF = os.path.join(HERE, "data", "reference_scores.jsonl")
RAW = os.path.join(HERE, "data", "jev_arm1_raw.jsonl")

positions = [json.loads(l) for l in open(POS)]
ref = [json.loads(l) for l in open(REF)]
raw = {}
for line in open(RAW):
    try:
        r = json.loads(line)
        raw[r["i"]] = r
    except Exception:
        pass
idx = sorted(i for i in raw if i < len(ref))
print("positions with both a jev answer and an oracle score: %d\n" % len(idx))

BINS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5),
        (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]


def reliability(indices):
    counts = [[0, 0, 0.0] for _ in BINS]   # n, n_correct, sum_stated
    for i in indices:
        probs = {int(k): v for k, v in raw[i]["probs"].items()}
        if not probs:
            continue
        best = ref[i]["best"]
        for d, p in probs.items():
            for b, (lo, hi) in enumerate(BINS):
                if lo <= p < hi:
                    counts[b][0] += 1
                    counts[b][1] += 1 if d == best else 0
                    counts[b][2] += p
                    break
    return counts


def ece(counts):
    tot = sum(c[0] for c in counts)
    if not tot:
        return float("nan")
    return sum(c[0] * abs((c[1] / c[0]) - (c[2] / c[0])) for c in counts if c[0]) / tot


def brier(indices, mode="jev"):
    tot, n = 0.0, 0
    for i in indices:
        probs = {int(k): v for k, v in raw[i]["probs"].items()}
        if not probs:
            continue
        best = ref[i]["best"]
        if mode == "uniform":
            probs = {d: 1.0 / len(probs) for d in probs}
        elif mode == "flattened":
            # Keep jev's RANKING, replace its magnitudes with the dataset-wide empirical
            # P(correct | rank). An arbitrary split would have made this baseline a
            # strawman; derived from the data it is the strongest rank-only predictor
            # available, so beating it means the magnitudes genuinely carry information.
            order = sorted(probs, key=probs.get, reverse=True)
            k = len(order)
            probs = {d: RANK_RATE.get((k, r), 1.0 / k) for r, d in enumerate(order)}
            tot_p = sum(probs.values()) or 1.0
            probs = {d: v / tot_p for d, v in probs.items()}
        tot += sum((p - (1.0 if d == best else 0.0)) ** 2 for d, p in probs.items())
        n += 1
    return tot / n if n else float("nan")


def rank_rates(indices):
    """Empirical P(this rank is the oracle's best), keyed by (n_legal, rank)."""
    hit, tot = {}, {}
    for i in indices:
        probs = {int(k): v for k, v in raw[i]["probs"].items()}
        if not probs:
            continue
        best = ref[i]["best"]
        order = sorted(probs, key=probs.get, reverse=True)
        for r, d in enumerate(order):
            key = (len(order), r)
            tot[key] = tot.get(key, 0) + 1
            hit[key] = hit.get(key, 0) + (1 if d == best else 0)
    return {k: hit[k] / tot[k] for k in tot if tot[k]}


RANK_RATE = rank_rates(idx)
print("empirical P(correct | rank), the rank-only baseline:")
for k in sorted(RANK_RATE):
    print("    %d legal, rank %d: %.3f" % (k[0], k[1], RANK_RATE[k]))
print()

counts = reliability(idx)
print("RELIABILITY (all positions)")
print("%-12s %8s %10s %10s %9s" % ("stated p", "n", "stated", "actual", "gap"))
for (lo, hi), c in zip(BINS, counts):
    if not c[0]:
        continue
    st, ac = c[2] / c[0], c[1] / c[0]
    print("%-12s %8d %10.3f %10.3f %+9.3f" % ("[%.1f,%.1f)" % (lo, hi), c[0], st, ac, ac - st))
print("\nECE (bin-weighted mean |actual - stated|): %.4f" % ece(counts))

print("\nBRIER vs oracle-best indicator (lower is better)")
bj, bu, bf = brier(idx, "jev"), brier(idx, "uniform"), brier(idx, "flattened")
print("  jev's distribution      %.4f" % bj)
print("  uniform over legal      %.4f" % bu)
print("  jev ranking, flattened  %.4f" % bf)
print("  -> magnitudes add %.1f%% over ranking alone" % (100 * (bf - bj) / bf if bf else float("nan")))

print("\nECE by game stage:")
groups = strata.group(positions)
for _, _, name in strata.STRATA:
    ii = [i for i in groups[name] if i in raw and i < len(ref)]
    if len(ii) < 50:
        continue
    mark = "  <- live regime" if name in strata.LIVE else ""
    print("  %-8s n=%-6d ECE %.4f   Brier %.4f%s" % (name, len(ii), ece(reliability(ii)), brier(ii), mark))

out = os.path.join(HERE, "results", "calibration.json")
with open(out, "w") as fh:
    json.dump({"n": len(idx), "ece": ece(counts), "brier_jev": bj,
               "brier_uniform": bu, "brier_flattened": bf,
               "bins": [{"lo": lo, "hi": hi, "n": c[0], "stated": (c[2] / c[0]) if c[0] else None,
                         "actual": (c[1] / c[0]) if c[0] else None}
                        for (lo, hi), c in zip(BINS, counts)]}, fh, indent=2)
print("\nwrote %s" % out)
