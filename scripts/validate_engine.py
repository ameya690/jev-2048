"""Cross-check Python board mechanics against the JS oracle engine.

If Python thinks a move is legal and the engine returns null for it (or vice versa),
every regret number downstream is computed over a mismatched action set. Run this
before trusting anything else.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import board  # noqa: E402
import oracle  # noqa: E402

N_GAMES = 6
MAX_MOVES = 400   # bounded: diversity of positions matters, not game completion
checked = 0
mismatches = []

with oracle.Oracle.from_config("d3_default") as orc:
    for gi in range(N_GAMES):
        rng = board.game_rng(10_000 + gi)
        grid = board.new_game(rng)
        moves = 0
        while moves < MAX_MOVES:
            py_legal = set(board.legal_moves(grid))
            res = orc.analyze(grid)
            js_legal = {d for d, s in enumerate(res["scores"]) if s is not None}
            checked += 1
            if py_legal != js_legal:
                mismatches.append((gi, list(grid), sorted(py_legal), sorted(js_legal)))
            if not py_legal:
                break
            # Drive with the oracle so we walk the same distribution the real run uses.
            d = res["best"]
            if d < 0:
                break
            grid, _ = board.move(grid, d)
            grid = board.spawn(grid, rng)
            moves += 1
        print("  game %d: %d positions checked" % (gi, checked), flush=True)

print("positions checked:", checked)
print("mismatches:", len(mismatches))
for m in mismatches[:5]:
    print("  game", m[0], "grid", m[1], "py", m[2], "js", m[3])
sys.exit(1 if mismatches else 0)
