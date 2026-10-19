"""Generate the oracle-rollout position set (Q9 arm A).

The oracle drives, so every arm scored on this file sees byte-identical positions --
which is what makes the paired comparisons in metrics.py work. Spawns come from
board.game_rng(game_index), so the whole set is reproducible from the seed alone.

Positions are SUBSAMPLED. A depth-3 oracle plays ~6,100 moves per game, so 20 games is
~122k positions -- but the confidence interval is driven by variation across the 20 game
CLUSTERS, not by within-game sample size, so scoring every 10th position costs ~1/10th
the jev calls and barely widens the CI. max_tile is recorded per position so results can
be stratified by game stage later.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402
import oracle  # noqa: E402

N_GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SAMPLE_EVERY = int(sys.argv[2]) if len(sys.argv) > 2 else 10
DRIVER = "d3_default"
OUT = os.path.join(HERE, "data", "oracle_rollout.jsonl")

t0 = time.time()
kept = total = 0
with oracle.Oracle.from_config(DRIVER) as orc, open(OUT, "w") as fh:
    for gi in range(N_GAMES):
        rng = board.game_rng(gi)
        grid = board.new_game(rng)
        ply = 0
        score = 0
        while True:
            res = orc.analyze(grid)
            if res["best"] < 0:
                break
            if ply % SAMPLE_EVERY == 0:
                fh.write(json.dumps({
                    "game": gi, "ply": ply, "grid": list(grid),
                    "max_tile": board.max_tile(grid),
                    "n_legal": len([s for s in res["scores"] if s is not None]),
                }) + "\n")
                kept += 1
            grid, gained = board.move(grid, res["best"])
            score += gained
            grid = board.spawn(grid, rng)
            ply += 1
            total += 1
        print("game %2d: %5d plies, score %7d, max tile %5d  [%.0fs]"
              % (gi, ply, score, board.max_tile(grid), time.time() - t0), flush=True)

print("\ntotal plies %d, sampled %d -> %s" % (total, kept, OUT))
