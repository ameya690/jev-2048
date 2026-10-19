"""The two bars jev has to clear.

legal_conditional_random is the kill-criterion bar. It is NOT uniform-over-4: a sensible
random agent samples from LEGAL moves, so its agreement with the oracle is 1/|legal|,
which rises as the board fills and is highest in the late game where decisions matter.
Benchmarking against a flat 25% would credit jev with a margin it has not earned.

heuristic_agent is the interesting bar: ~40 lines of hand-written scoring, no search.
If jev cannot beat this, the honest answer is to write the heuristic.
"""
import board


def legal_conditional_random(grid, rng):
    legal = board.legal_moves(grid)
    return rng.choice(legal) if legal else -1


def _score_board(grid):
    """Monotonicity + smoothness + empty cells + corner bonus. Exponent space."""
    empty = sum(1 for v in grid if v == 0)

    mono = 0.0
    for k in range(4):
        row = grid[k * 4:k * 4 + 4]
        col = [grid[k], grid[k + 4], grid[k + 8], grid[k + 12]]
        for line in (row, col):
            inc = sum(max(0, line[i + 1] - line[i]) for i in range(3))
            dec = sum(max(0, line[i] - line[i + 1]) for i in range(3))
            mono -= min(inc, dec)

    smooth = 0.0
    for r in range(4):
        for c in range(4):
            v = grid[r * 4 + c]
            if v == 0:
                continue
            if c < 3 and grid[r * 4 + c + 1]:
                smooth -= abs(v - grid[r * 4 + c + 1])
            if r < 3 and grid[(r + 1) * 4 + c]:
                smooth -= abs(v - grid[(r + 1) * 4 + c])

    mx = max(grid)
    corner = 1.0 if mx in (grid[0], grid[3], grid[12], grid[15]) else 0.0

    return 2.7 * empty + 1.0 * mono + 0.1 * smooth + 3.0 * corner + 0.0005 * sum(1 << v for v in grid if v)


def heuristic_agent(grid):
    """Greedy 1-ply over the hand heuristic. No lookahead past the immediate move."""
    best, best_score = -1, float("-inf")
    for d in board.legal_moves(grid):
        nxt, _ = board.move(grid, d)
        s = _score_board(nxt)
        if s > best_score:
            best_score, best = s, d
    return best
