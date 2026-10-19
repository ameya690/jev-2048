"""Per-move regret measured on each agent's OWN rollouts -- the fair comparison.

Arm 1 scored every agent on positions the ORACLE generated, which is the right way to
compare judgment on identical boards. But jev's own games produce different, messier
boards, so "jev forfeits 29.8% on its own rollouts" cannot be set against "random forfeits
30.4% on the oracle's rollouts". Each agent has to be scored on the boards it actually
creates. No API calls: random and the heuristic play locally, the oracle scores.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import baselines  # noqa: E402
import board  # noqa: E402
import metrics  # noqa: E402
import oracle  # noqa: E402

N = 10
out = {}
with oracle.Oracle.from_config("d5_default") as orc:
    for label in ("random", "heuristic"):
        refs, moves, gids, plies, scores, tiles = [], [], [], [], [], []
        for gi in range(N):
            rng = board.game_rng(gi)
            pick = random.Random(9000 + gi)
            grid = board.new_game(rng)
            n = sc = 0
            while True:
                legal = board.legal_moves(grid)
                if not legal:
                    break
                ev = orc.analyze(grid)
                d = (baselines.heuristic_agent(grid) if label == "heuristic"
                     else baselines.legal_conditional_random(grid, pick))
                refs.append({"scores": ev["scores"], "best": ev["best"]})
                moves.append(d)
                gids.append(gi)
                grid, g = board.move(grid, d)
                sc += g
                grid = board.spawn(grid, rng)
                n += 1
            plies.append(n)
            scores.append(sc)
            tiles.append(board.max_tile(grid))
        m, lo, hi, ng = metrics.spread_weighted_regret(refs, moves, gids)
        agree = sum(1 for r, d in zip(refs, moves) if r["best"] == d) / len(moves)
        out[label] = (m, lo, hi, sorted(plies)[N // 2], sorted(scores)[N // 2], max(tiles), agree)
        print("%-10s regret %.4f [%.4f, %.4f] | median %4d plies, %6d score, best tile %4d | matched %.0f%%"
              % (label, m, lo, hi, out[label][3], out[label][4], out[label][5], 100 * agree), flush=True)

# jev, from the games it actually played
games = [json.loads(l) for l in open(os.path.join(HERE, "data", "jev_games.jsonl"))]
refs = [{"scores": p["oracle_scores"], "best": p["oracle_best"]} for g in games for p in g["plies"]]
moves = [p["choice"] for g in games for p in g["plies"]]
gids = [g["game"] for g in games for p in g["plies"]]
m, lo, hi, ng = metrics.spread_weighted_regret(refs, moves, gids)
agree = sum(1 for r, d in zip(refs, moves) if r["best"] == d) / len(moves)
pl = sorted(g["n_plies"] for g in games)[len(games) // 2]
scm = sorted(g["final_score"] for g in games)[len(games) // 2]
print("%-10s regret %.4f [%.4f, %.4f] | median %4d plies, %6d score, best tile %4d | matched %.0f%%"
      % ("jev", m, lo, hi, pl, scm, max(g["max_tile"] for g in games), 100 * agree))
