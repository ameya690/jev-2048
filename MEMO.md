# Does jev belong in a sequential decision loop?

**Decision memo — personal due diligence. Kill criterion written 2026-10-18, before any measurement.**

## The question this answers

Not "can jev solve 2048." That was a category error: jev is a System One model with no
lookahead, 2048 rewards search, and a failure would have been uninterpretable — bad
classification or just the expected result of handing a no-search model a search problem.

The question is **does jev's calibrated output carry enough information to drive a
sequential decision loop, and do its errors compound or stay bounded.** 2048 is the
instrument, not the subject: it is one of the few domains where the correct answer is
exactly computable, so a calibration claim can be checked against ground truth rather
than taken on faith.

## Kill criterion — committed in advance

**Stop after Arm 1 if jev's mean normalized regret on oracle-rollout positions is not
clearly better than the legal-conditional random baseline**, where "clearly" means the
paired 95% CI on the difference excludes zero.

If that fails, the answer is "don't build on jev for sequential decisions," it cost an
afternoon, and Arms 2-5 are cancelled. **Everything after Arm 1 is optional.** The named
failure mode of this project is building all five arms because they are already designed.

## What "good" looks like

**Metric correction, made after measuring.** The planned metric was per-position
normalised regret, `(EV_best - EV_chosen) / (EV_best - EV_worst)`, on positions whose EV
spread clears a threshold. A sensitivity sweep (`scripts/floor_sensitivity.py`) showed
the threshold is **not** a neutral knob: the heuristic-vs-random ratio moves from 7.3x to
35.8x across reasonable choices, and the oracle ceiling moves 12x. The cause is
structural -- dividing each position by its own spread makes a trivial decision weigh as
much as a decisive one, so an agent forfeiting 90% of a negligible spread scores 0.9.
The threshold was crudely compensating for that.

The primary metric is therefore **spread-weighted regret**: total EV forfeited divided by
total EV available, summed over positions. Small-spread positions contribute little to
both numerator and denominator, which is what the threshold was approximating, and it
needs no threshold at all. Per-position floored regret is still reported as a secondary,
and the two agree closely at the floor that was originally chosen -- that choice turned
out to be near the principled answer, but it was luck, not reasoning.

0.0 is oracle-equivalent, 1.0 is worst-move-every-time.
Reference points, all measured not assumed:

| Agent | Expected normalized regret |
|---|---|
| Oracle (self, varied heuristic) | the ceiling — **not 0**; see results/self_agreement.json |
| Hand heuristic (mono + smooth + empty) | the bar jev must clear to be interesting |
| Legal-conditional random | the bar jev must clear to be worth continuing |

The random baseline is **not** 25% top-1 accuracy. A sensible random agent samples from
*legal* moves, so its agreement is 1/|legal|. Measured on the oracle-rollout set:
**28.7%**, from 67.9% of positions having 4 legal moves, 26.2% having 3, 5.9% having 2.
The effect is modest here because strong play keeps the board open; it will be larger on
jev's own rollouts, where the board clogs. Compute it per position set, never carry it
across.

## Measured: what a search-free agent actually reaches

Both baselines, 20 games each, same CRN seeds as the oracle rollout:

| Agent | Median plies | Median score | ≥512 | ≥1024 | ≥2048 |
|---|---|---|---|---|---|
| Hand heuristic (1-ply, no search) | 508 | 7,392 | 15/20 | 1/20 | 0/20 |
| Legal-conditional random | 103 | 856 | 0/20 | 0/20 | 0/20 |

**A no-search agent lives at 512.** This is the provisional answer to "how far does pure
pattern-matching get you with zero search" — and it is a lower bound, since a 1-ply greedy
heuristic is a weak proxy for human intuition, which does implicit lookahead.

It also forces stratification. The oracle rollout reaches 4096-8192 and spends 75% of its
plies above the 4096 tile; only 11.1% of positions sit at or below 512. Grading jev on the
unstratified set would mostly measure its judgment on boards it would never create. All
results are therefore reported per game-stage stratum, and the `<=256` / `512` rows are
the live regime.

## STEP 1 COMPLETE: the ceiling

9,193 positions from 20 oracle-driven games. Reference is depth-5 expectimax with the
default heuristic; the comparisons are a shallower search and a different value function.
Cross-regret is spread-weighted, so the ceiling is on exactly the scale jev is scored on.

| config | top-1 agreement | cross-regret vs reference |
|---|---|---|
| depth-3, same heuristic | 75.6% | 0.0015 [0.0012, 0.0019] |
| depth-5, alternate weights | 81.9% | 0.0007 [0.0005, 0.0008] |

**Two reasonable expectimax configurations disagree on a quarter of all positions while
forfeiting ~0.15% of available value.** Agreement and quality are nearly unrelated here.

By game stage, and this is the part that matters:

| stratum | n | depth-3 | alt weights |
|---|---|---|---|
| <=256 | 528 | 0.0027 | 0.0045 |
| 512 | 495 | 0.0019 | 0.0021 |
| 1024 | 963 | 0.0020 | 0.0012 |
| 2048 | 1772 | 0.0014 | 0.0007 |
| >=4096 | 5435 | 0.0015 | 0.0005 |

**The ceiling is loosest exactly where a search-free agent lives.** Reasonable oracles
disagree 3-9x more on early boards than late ones, because an early position is less
determined -- there is genuinely more than one defensible move. So jev's scores in the
live regime must be read against ~0.004, not against the 0.0007 the late game suggests.

The scale jev will be placed on, in the live regime (<=256):

    ceiling   ~0.004   |   hand heuristic  0.028   |   random  0.298

About 75x of range between the ceiling and random, with the heuristic sitting ~7x above
the ceiling. Ample resolution to tell a real result from noise.

## RESULTS: jev 1.13, 9,193 positions, 20 games, $0.22 total

### Arm 1 -- move quality, illegal moves masked

| agent | spread-weighted regret | 95% CI | top-1 |
|---|---|---|---|
| oracle ceiling (d3 vs d5) | 0.0015 | [0.0012, 0.0019] | 75.6% |
| hand heuristic | 0.0111 | [0.0086, 0.0136] | 44.2% |
| **jev 1.13** | **0.1222** | **[0.1013, 0.1432]** | **38.7%** |
| legal-conditional random | 0.3039 | [0.2885, 0.3193] | 28.5% |

**Kill criterion: PASS.** Paired jev - random = -0.1816 [-0.2085, -0.1548], excludes zero.
**But jev loses to the hand heuristic by +0.1112 [+0.0913, +0.1310]** -- 11x worse than
~40 lines of no-search scoring, and ~80x worse than the ceiling. Flat across game stages
(0.091 to 0.125), so this is not a late-game collapse; it is uniform mediocrity.

### Calibration -- the question 2048 was chosen to answer

ECE 0.0435, which reads as decently calibrated. The Brier decomposition says otherwise:

| predictor | Brier (lower better) |
|---|---|
| jev's distribution | 0.7047 |
| uniform over legal moves | 0.7135 |
| **jev's ranking, magnitudes replaced by empirical rank frequencies** | **0.6978** |

**jev's probability magnitudes carry no information beyond their ordering -- they are
1.0% WORSE than discarding them.** And the ordering itself is thin: with four legal moves,
P(correct) by jev's rank is 0.351 / 0.207 / 0.184 / 0.258. Its *least* favoured move is
right more often than its 2nd and 3rd choices. Only the top pick beats chance.

The good ECE is an artifact of jev rarely being confident: its mass sits in [0.1, 0.5], and
being calibrated while always saying "unsure" is easy. Calibration in the ECE sense is real
but nearly decision-irrelevant here.

### Illegal moves -- Q10's second metric, 2,000 positions, all four offered

| legal moves available | positions | jev picked an illegal move | uniform chance would be |
|---|---|---|---|
| 4 | 1,384 | 0.00% | 0% |
| 3 | 530 | **39.8%** | 25% |
| 2 | 86 | **67.4%** | 50% |

**jev picks illegal moves MORE often than uniform chance would.** It is not merely failing
to model the board, it is attracted to the illegal direction. Plausible mechanism: an
illegal move is one where tiles are already packed that way -- often toward the corner
holding the big tile -- which is exactly where a surface reading of "good 2048 play" points.
Mean probability mass on illegal moves is 0.10, rising with game stage.

## REVISIONS AFTER REVIEW

Four changes, three of them because the review was right.

**1. The encoding was a design error of mine, worth ~a third of jev's regret.** Q11 chose
a raw 4x4 numeric grid with no derived features. Re-running all 9,193 positions with the
same board described in sentences ("The top row, left to right, is 2, 4, 8, empty."):

| agent | regret | 95% CI | share of random->oracle gap recovered |
|---|---|---|---|
| oracle ceiling | 0.0015 | [0.0012, 0.0019] | 99.5% |
| hand heuristic | 0.0111 | [0.0086, 0.0136] | 96.4% |
| **jev, prose** | **0.0821** | **[0.0617, 0.1025]** | **73.0%** |
| jev, raw grid | 0.1222 | [0.1013, 0.1432] | 59.8% |
| legal-conditional random | 0.3039 | [0.2885, 0.3193] | 0% |

Paired prose - raw grid = -0.0401 [-0.0543, -0.0259]. Real. But prose still loses to the
hand heuristic by +0.0711 [+0.0515, +0.0906]. **The verdict is unchanged; the margin is
7x rather than 11x.**

A caveat on my own ablation: the 1,000-position subsample that motivated this took 200
per stratum, which over-weights the early game relative to the real distribution and
suggested 0.0564. The full run gives 0.0821. Equal-per-stratum sampling is not the
population.

**2. Encoding does NOT explain the legality blindness.** Same prose encoding, unmasked:

| legal moves | raw grid | prose | chance |
|---|---|---|---|
| 3 | 39.8% | 41.5% | 25% |
| 2 | 67.4% | 70.9% | 50% |

No improvement, slightly worse. **jev uses better-formatted information to make better
judgments, but still cannot tell which moves are valid in any format.** That dissociation
is the most useful thing in this memo.

**3. The attraction hypothesis survives a real test.** jev's illegal picks point toward
the max tile's half 84.8% of the time, against a control of 74.1% for all illegal options
available (illegal moves are themselves structurally biased that way). Excess +10.7pp.

**4. The ranking claim was overstated, and the calibration claim weakens.** Bootstrapping
over whole games, 2,000 resamples: rank3 - rank2 = +0.075 [+0.008, +0.136] is real, but
rank3 - rank1 = +0.052 [-0.019, +0.120] is noise. I had claimed both. And
Brier(jev) - Brier(uniform) = -0.0088 [-0.0192, +0.0012] -- **not distinguishable from
uniform**, where I had said "barely beats uniform" as if settled.

## DECISION: do not build on jev for sequential decisions in this shape

The kill criterion passed, and the kill criterion was wrong -- necessary but not
sufficient. Beating random was never a meaningful bar; it only looked like one before the
heuristic was measured. The three results together:

1. jev is 7x worse than hand-written scoring it would have to replace (prose
   encoding; 11x on the raw grid). It recovers 73% of the random-to-oracle gap where
   the heuristic recovers 96%.
2. Its probability distribution is not distinguishable from uniform once CIs
   respect game clustering, and its magnitudes add nothing over their own ranking.
3. It does not model board legality, masking was silently doing that reasoning for
   it, and a better encoding fixes move quality WITHOUT fixing legality at all.

Point 3 is the one that generalises past 2048. In any sequential loop, the harness must
enumerate valid actions for jev, because jev will not. That is a real constraint on where
a System One model fits -- it is a classifier over options you have already computed, not
something that reasons about what the options are.

Arms 2-5 are cancelled. Arm 3 (jev as a value function inside search) is the only one that
could still be interesting, and result 2 makes it unlikely to work: a value function built
from these probabilities would be built on noise.

## Two results that landed before jev was involved

**1. Accuracy understates agent quality by ~17x, and would have misled us.**

Measured on 9,193 oracle-rollout positions, 20 games:

| agent | top-1 agreement | normalised regret | share of available EV captured |
|---|---|---|---|
| hand heuristic | 44.2% | 0.0114 | 98.9% |
| legal-conditional random | 28.5% | 0.3007 | 69.9% |

By top-1 agreement the heuristic looks 1.6x better than random. By regret it is **26x**
better. It disagrees with the oracle on 56% of positions, but those disagreements are
almost all between near-equivalent moves and cost nothing. The originally proposed metric
-- top-1 agreement with partial credit for second-best -- would have read 44% and called
the heuristic mediocre. It is near-oracle.

**2. One percent per-decision regret produces a 16x worse outcome.**

The hand heuristic captures 98.9% of available expected value per move and reaches the
512 tile. The oracle reaches 8192. That is the error-compounding thesis, quantified,
without jev: per-decision quality and game outcome are only weakly coupled, and a
"95% of value captured" headline would badly overstate what an agent does in a live loop.

Both numbers come from positions the ORACLE generated. On an agent's own rollouts the
boards are messier and regret will be worse -- which is what the Q9 oracle-rollout vs
jev-rollout gap measures, and why it is the headline.

## Reading order for results

1. **Oracle self-agreement** — the ceiling. Measured first, with no jev involved.
2. **Oracle-rollout vs jev-rollout gap** — whether jev's errors self-compound. This is
   the single most transferable fact, and it governs deploying *any* System One model
   inside a sequential loop.
3. **Calibration** — do the ordinal-bucket evaluator (Arm 3) and k=5 self-consistency
   (Arm 4) agree that the probabilities carry information beyond their ranking?
4. **Fraction of inconsequential positions** — free from the instrumentation, and
   nobody has published it.

**The 2048 score is the least interesting number here. Do not lead with it.**
