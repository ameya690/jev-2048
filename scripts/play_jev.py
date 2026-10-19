"""Let jev actually PLAY 2048, logging every decision. This is Arm 2 (jev-rollout).

Arm 1 only ever scored jev on boards the ORACLE produced -- clean, well-structured
positions a strong player creates. Here jev drives, so it faces the mess its own mistakes
make. The gap between the two is the error-compounding result the design was built around.

Prose encoding (the better one) and illegal moves masked, which is what any deployment
would do. Spawns come from board.game_rng(game_index), the same CRN seeds the oracle
games used, so game i has an identical random sequence for both players.

Every ply records jev's choice and distribution alongside the oracle's valuation of all
four moves, so the replay can show not just what jev did but what it cost.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402
import jev_client  # noqa: E402
import metrics  # noqa: E402
import oracle  # noqa: E402

ROWNAMES = ["top", "second", "third", "bottom"]


def prose(grid):
    return " ".join(
        "The %s row, left to right, is %s." % (
            ROWNAMES[r], ", ".join("%d" % (1 << v) if v else "empty" for v in grid[r * 4:r * 4 + 4]))
        for r in range(4))


N_GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 10
OUT = os.path.join(HERE, "data", "jev_games.jsonl")
key = jev_client.load_key()
url, model = jev_client.endpoint_for(key)

done_games = set()
if os.path.exists(OUT):
    for line in open(OUT):
        try:
            done_games.add(json.loads(line)["game"])
        except Exception:
            pass

t0 = time.time()
spent = 0.0
with oracle.Oracle.from_config("d5_default") as orc, open(OUT, "a") as fh:
    for gi in range(N_GAMES):
        if gi in done_games:
            print("game %d cached" % gi, flush=True)
            continue
        rng = board.game_rng(gi)
        grid = board.new_game(rng)
        plies, score = [], 0
        while True:
            legal = board.legal_moves(grid)
            if not legal:
                break
            ev = orc.analyze(grid)
            body, dirs = jev_client.build_request(grid, model, mask_illegal=True)
            body["state"] = jev_client.RULES + "\n\n" + prose(grid)
            try:
                payload = jev_client.post(url, key, body)
            except Exception as e:
                print("  game %d ply %d failed: %r" % (gi, len(plies), e), flush=True)
                break
            d, probs, conf, cost = jev_client.parse_response(payload)
            spent += cost or 0.0
            if d < 0 or d not in legal:
                d = legal[0]
            reg = metrics.normalized_regret(ev["scores"], d, 0.0)
            plies.append({
                "grid": list(grid), "choice": d,
                "probs": {board.DIR_NAMES[k]: round(v, 3) for k, v in probs.items()},
                "confidence": conf,
                "oracle_best": ev["best"],
                "oracle_scores": [None if s is None else round(s, 1) for s in ev["scores"]],
                "regret": None if reg is None else round(reg, 4),
                "score": score,
            })
            grid, gained = board.move(grid, d)
            score += gained
            grid = board.spawn(grid, rng)
        rec = {"game": gi, "plies": plies, "final_grid": list(grid),
               "final_score": score, "max_tile": board.max_tile(grid), "n_plies": len(plies)}
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        agree = sum(1 for p in plies if p["choice"] == p["oracle_best"]) / max(1, len(plies))
        print("game %2d: %4d plies, score %6d, max tile %5d, agreed with oracle %.0f%%  [%.0fs $%.3f]"
              % (gi, len(plies), score, board.max_tile(grid), 100 * agree, time.time() - t0, spent), flush=True)

print("\n%d games, %.0fs, $%.4f -> %s" % (N_GAMES, time.time() - t0, spent, OUT))
