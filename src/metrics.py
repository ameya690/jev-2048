"""Normalised regret and cluster-robust statistics.

REGRET. The engine's expected values are in heuristic units (~1.6e6 baseline) and the
spread between moves is frequently <1e-6 -- two moves on a symmetric board can differ
in the 10th significant digit. So:
  - absolute regret is uninterpretable,
  - relative-to-best regret is useless (everything is ~1.6e6),
  - (best - chosen) / (best - worst) is the only form that carries signal,
and it REQUIRES a spread floor, or near-tied positions divide by ~0 and explode.

Positions below the floor are 'inconsequential' -- every legal move is equivalent and
the agent cannot be graded. They are excluded from the regret mean and reported as
their own number, because what fraction of 2048 decisions are free is itself a result.

STATISTICS. Positions within a game are heavily correlated, so the unit of analysis is
the GAME, not the position. Mean regret is the mean of per-game means; its standard
error comes from variation ACROSS games. A CI computed over 20k positions would look
roughly ten times tighter than the truth.
"""
import math


def spread(scores):
    """EV range across legal moves. None if fewer than 2 legal moves (no decision)."""
    vals = [s for s in scores if s is not None]
    if len(vals) < 2:
        return None
    return max(vals) - min(vals)


def normalized_regret(scores, chosen, spread_floor):
    """Fraction of available EV forfeited, in [0, 1].

    Returns None when the position carries no signal: fewer than 2 legal moves, or a
    spread below the floor. Returns 1.0 for an illegal choice (worst possible).
    """
    vals = [s for s in scores if s is not None]
    if len(vals) < 2:
        return None
    best, worst = max(vals), min(vals)
    # Exactly-equal EVs happen (symmetric boards), and a zero spread is ungradeable no
    # matter what the floor is -- every move forfeits nothing. Checked separately so the
    # function is safe at spread_floor=0, which the floor sensitivity sweep uses.
    if best == worst or best - worst < spread_floor:
        return None
    if chosen < 0 or scores[chosen] is None:
        return 1.0
    return (best - scores[chosen]) / (best - worst)


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def game_means(per_position, game_ids):
    """Collapse positions to one value per game. Games with no gradeable position drop."""
    acc = {}
    for v, g in zip(per_position, game_ids):
        if v is None:
            continue
        acc.setdefault(g, []).append(v)
    return {g: _mean(vs) for g, vs in acc.items()}


def clustered_mean_ci(per_position, game_ids, z=1.96):
    """Mean and CI with GAMES as the cluster. Returns (mean, lo, hi, n_games)."""
    gm = game_means(per_position, game_ids)
    vals = list(gm.values())
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    m = _mean(vals)
    if n == 1:
        return m, float("nan"), float("nan"), 1
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    se = math.sqrt(var / n)
    return m, m - z * se, m + z * se, n


def paired_clustered_ci(a_per_position, b_per_position, game_ids, z=1.96):
    """CI on the mean of (a - b) over positions where BOTH are gradeable.

    This is the comparison that matters: with common random numbers, every arm is scored
    on byte-identical positions, so the paired difference removes all between-position
    variance. With only ~20 game clusters, that pairing is doing most of the work in
    separating a real effect from noise.
    """
    diffs, gids = [], []
    for a, b, g in zip(a_per_position, b_per_position, game_ids):
        if a is None or b is None:
            continue
        diffs.append(a - b)
        gids.append(g)
    return clustered_mean_ci(diffs, gids, z=z)


def choose_spread_floor(spreads, quantile=0.25):
    """Pick the floor empirically from the observed spread distribution.

    It cannot be set a priori: the units are the heuristic's, not game score. Default
    drops the bottom quartile of decisions as inconsequential.
    """
    vals = sorted(s for s in spreads if s is not None)
    if not vals:
        return 0.0
    return vals[min(len(vals) - 1, int(quantile * len(vals)))]


def spread_weighted_regret(ref_scores, chosen_moves, game_ids):
    """Total EV forfeited / total EV available, aggregated. NO floor needed.

    Per-position normalisation was a mistake: dividing each position by its own spread
    makes a trivial decision weigh as much as a decisive one, so a weak agent forfeiting
    90% of a negligible spread scores 0.9. That is why the floor-sensitivity sweep showed
    the headline moving 5x with the floor -- the floor was doing the work of excluding
    positions the metric should never have weighted equally in the first place.

    Summing numerator and denominator instead makes small-spread positions contribute
    little to both, which is the behaviour the floor was crudely approximating. The
    aggregate is the fraction of available value the agent actually forfeits.

    Returns (ratio, lo, hi, n_games), clustered with the per-game ratio as the unit.
    """
    per_game_num, per_game_den = {}, {}
    for r, d, g in zip(ref_scores, chosen_moves, game_ids):
        vals = [s for s in r["scores"] if s is not None]
        if len(vals) < 2:
            continue
        best, worst = max(vals), min(vals)
        if best == worst:
            continue
        got = worst if (d < 0 or r["scores"][d] is None) else r["scores"][d]
        per_game_num[g] = per_game_num.get(g, 0.0) + (best - got)
        per_game_den[g] = per_game_den.get(g, 0.0) + (best - worst)
    ratios = [per_game_num[g] / per_game_den[g] for g in sorted(per_game_den) if per_game_den[g] > 0]
    n = len(ratios)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    m = sum(ratios) / n
    if n == 1:
        return m, float("nan"), float("nan"), 1
    var = sum((v - m) ** 2 for v in ratios) / (n - 1)
    se = math.sqrt(var / n)
    return m, m - 1.96 * se, m + 1.96 * se, n


def _per_game_ratio(ref_scores, chosen_moves, game_ids):
    num, den = {}, {}
    for r, d, g in zip(ref_scores, chosen_moves, game_ids):
        vals = [s for s in r["scores"] if s is not None]
        if len(vals) < 2:
            continue
        best, worst = max(vals), min(vals)
        if best == worst:
            continue
        got = worst if (d < 0 or r["scores"][d] is None) else r["scores"][d]
        num[g] = num.get(g, 0.0) + (best - got)
        den[g] = den.get(g, 0.0) + (best - worst)
    return {g: num[g] / den[g] for g in den if den[g] > 0}


def paired_spread_weighted(ref_scores, moves_a, moves_b, game_ids):
    """CI on (A - B) in spread-weighted regret, paired within game.

    Both agents are scored on identical positions (common random numbers), so pairing
    removes between-game difficulty variance -- which is doing most of the work with only
    ~20 clusters. Returns (mean_diff, lo, hi, n_games); negative means A forfeits less.
    """
    ra = _per_game_ratio(ref_scores, moves_a, game_ids)
    rb = _per_game_ratio(ref_scores, moves_b, game_ids)
    diffs = [ra[g] - rb[g] for g in sorted(set(ra) & set(rb))]
    n = len(diffs)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    m = sum(diffs) / n
    if n == 1:
        return m, float("nan"), float("nan"), 1
    var = sum((v - m) ** 2 for v in diffs) / (n - 1)
    se = math.sqrt(var / n)
    return m, m - 1.96 * se, m + 1.96 * se, n
