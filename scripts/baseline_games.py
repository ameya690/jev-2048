"""How strong are the two baselines when they actually play? No jev, no oracle.

Two things this establishes:
  1. Whether the hand heuristic is a real bar. If ~40 lines of no-search scoring already
     reaches 1024, jev has to clear something meaningful to be interesting.
  2. What board regime a no-search agent occupies -- which decides whether the
     oracle-rollout position set (75% of it above the 4096 tile) overlaps jev's own
     games at all, and therefore how to stratify.
Uses the same CRN seeds as the oracle rollout, so game i is the same spawn sequence.
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import baselines  # noqa: E402
import board  # noqa: E402

N_GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 20

for label in ("heuristic", "random"):
    tiles, plies, scores = Counter(), [], []
    for gi in range(N_GAMES):
        rng = board.game_rng(gi)
        pick_rng = __import__("random").Random(9000 + gi)
        grid = board.new_game(rng)
        score = ply = 0
        while True:
            d = (baselines.heuristic_agent(grid) if label == "heuristic"
                 else baselines.legal_conditional_random(grid, pick_rng))
            if d < 0:
                break
            grid, gained = board.move(grid, d)
            score += gained
            grid = board.spawn(grid, rng)
            ply += 1
        tiles[board.max_tile(grid)] += 1
        plies.append(ply)
        scores.append(score)
    print("%-10s  median plies %5d  median score %7d  max tile distribution:"
          % (label, sorted(plies)[len(plies) // 2], sorted(scores)[len(scores) // 2]))
    for t in sorted(tiles):
        print("            %6d : %2d/%d games" % (t, tiles[t], N_GAMES))
    reached = lambda th: sum(c for t, c in tiles.items() if t >= th)  # noqa: E731
    print("            reaches >=512: %d/%d, >=1024: %d/%d, >=2048: %d/%d\n"
          % (reached(512), N_GAMES, reached(1024), N_GAMES, reached(2048), N_GAMES))
