"""Two follow-ups from review, both answerable from data already collected.

(A) IS THE ILLEGAL-MOVE ATTRACTION REAL? The claim was that jev is drawn to illegal
    moves because they point toward where tiles are already stacked. That is testable.
    For each unmasked position, classify each direction as pointing "toward" the max
    tile's half of the board (exactly 2 of 4 directions always qualify, so the base rate
    is 50%). Then compare jev's illegal picks against the directions that were ILLEGAL
    AND AVAILABLE at that position -- the right control, because illegal moves are
    themselves structurally biased toward the packed side. Attraction means jev's rate
    exceeds that control, not merely that it exceeds 50%.

(B) IS THE RANKING ODDITY NOISE? P(correct|rank) was pooled over 9,193 positions from
    only 20 games, with strong within-game correlation -- so the claim that jev's 4th
    choice beats its 2nd and 3rd needs a CI that respects clustering. Bootstrap over
    whole GAMES, not positions. Same treatment for the Brier comparisons.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402

pos = [json.loads(l) for l in open(os.path.join(HERE, "data", "oracle_rollout.jsonl"))]
ref = [json.loads(l) for l in open(os.path.join(HERE, "data", "reference_scores.jsonl"))]
arm1 = {}
for l in open(os.path.join(HERE, "data", "jev_arm1_raw.jsonl")):
    r = json.loads(l)
    arm1[r["i"]] = r
unmasked = [json.loads(l) for l in open(os.path.join(HERE, "data", "jev_unmasked_raw.jsonl"))]


def toward(d, grid):
    """Does direction d point toward the half of the board holding the max tile?"""
    mx = max(range(16), key=lambda i: grid[i])
    r, c = mx // 4, mx % 4
    return {board.UP: r <= 1, board.DOWN: r >= 2, board.LEFT: c <= 1, board.RIGHT: c >= 2}[d]


print("=" * 72)
print("(A) ILLEGAL-MOVE ATTRACTION: does jev's illegal pick point at the big tile?")
print("=" * 72)
picked_toward = picked_n = 0
ctrl_toward = ctrl_n = 0
for r in unmasked:
    grid = pos[r["i"]]["grid"]
    legal = set(r["legal"])
    illegal_avail = [d for d in (board.UP, board.RIGHT, board.DOWN, board.LEFT) if d not in legal]
    if not illegal_avail:
        continue
    for d in illegal_avail:                      # control: all illegal options available
        ctrl_n += 1
        ctrl_toward += 1 if toward(d, grid) else 0
    if not r["was_legal"]:                       # jev actually chose an illegal move
        picked_n += 1
        picked_toward += 1 if toward(r["choice"], grid) else 0

print("  jev's illegal picks pointing toward max tile : %d/%d = %.1f%%"
      % (picked_toward, picked_n, 100.0 * picked_toward / max(1, picked_n)))
print("  CONTROL, all illegal options available       : %d/%d = %.1f%%"
      % (ctrl_toward, ctrl_n, 100.0 * ctrl_toward / max(1, ctrl_n)))
print("  (unconditional base rate is 50%% by construction)")
diff = 100.0 * (picked_toward / max(1, picked_n) - ctrl_toward / max(1, ctrl_n))
print("  excess over control: %+.1f pp  -> %s"
      % (diff, "attraction supported" if diff > 5 else
         ("attraction NOT supported" if diff < 5 else "inconclusive")))

print()
print("=" * 72)
print("(B) RANK ODDITY + CALIBRATION, bootstrapped over GAMES (n=20 clusters)")
print("=" * 72)
by_game = {}
for i, p in enumerate(pos):
    if i in arm1:
        by_game.setdefault(p["game"], []).append(i)
games = sorted(by_game)


def rank_rates(indices, nlegal=4):
    hit = {}
    tot = {}
    for i in indices:
        probs = {int(k): v for k, v in arm1[i]["probs"].items()}
        if len(probs) != nlegal:
            continue
        best = ref[i]["best"]
        for rk, d in enumerate(sorted(probs, key=probs.get, reverse=True)):
            tot[rk] = tot.get(rk, 0) + 1
            hit[rk] = hit.get(rk, 0) + (1 if d == best else 0)
    return {rk: hit[rk] / tot[rk] for rk in tot if tot[rk]}


def brier_delta(indices):
    """jev's distribution minus uniform-over-legal. Negative = jev better."""
    tj = tu = n = 0.0
    for i in indices:
        probs = {int(k): v for k, v in arm1[i]["probs"].items()}
        if not probs:
            continue
        best = ref[i]["best"]
        u = 1.0 / len(probs)
        tj += sum((p - (1.0 if d == best else 0.0)) ** 2 for d, p in probs.items())
        tu += sum((u - (1.0 if d == best else 0.0)) ** 2 for d in probs)
        n += 1
    return (tj - tu) / n if n else float("nan")


point = rank_rates([i for g in games for i in by_game[g]])
rng = random.Random(7)
B = 2000
boot_rank = {rk: [] for rk in point}
boot_delta = []
for _ in range(B):
    samp = [rng.choice(games) for _ in games]
    idx = [i for g in samp for i in by_game[g]]
    rr = rank_rates(idx)
    for rk in boot_rank:
        if rk in rr:
            boot_rank[rk].append(rr[rk])
    boot_delta.append(brier_delta(idx))


def ci(xs):
    xs = sorted(xs)
    return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs))]


print("  P(correct | jev's rank), 4-legal positions, %d game-bootstrap resamples:" % B)
for rk in sorted(point):
    lo, hi = ci(boot_rank[rk])
    print("    rank %d: %.3f  95%% CI [%.3f, %.3f]" % (rk, point[rk], lo, hi))
r = sorted(point)
if len(r) >= 4:
    # a is the rank-3 draw, b the comparison draw -- subtract in the labelled order
    for other in (1, 2):
        gaps = [a - b for a, b in zip(boot_rank[3], boot_rank[other])]
        lo, hi = ci(gaps)
        print("    rank3 - rank%d: %+.3f  95%% CI [%+.3f, %+.3f]  -> %s"
              % (other, point[3] - point[other], lo, hi,
                 "REAL (CI excludes 0)" if lo > 0 or hi < 0 else "NOISE (CI spans 0)"))

d = brier_delta([i for g in games for i in by_game[g]])
lo, hi = ci(boot_delta)
print("\n  Brier(jev) - Brier(uniform): %+.4f  95%% CI [%+.4f, %+.4f]" % (d, lo, hi))
print("    -> %s" % ("jev's distribution beats uniform" if hi < 0 else
                     ("indistinguishable from uniform" if lo < 0 < hi else "worse than uniform")))
