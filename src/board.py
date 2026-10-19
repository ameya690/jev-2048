"""2048 mechanics, ported line-for-line from the vendored engine's test harness so the
Python game loop and the JS oracle agree on legality exactly.

Boards are 16 exponents, row-major, 0 = empty. Tile value is 2**exponent.
Directions: 0 up, 1 right, 2 down, 3 left.
"""
import random

UP, RIGHT, DOWN, LEFT = 0, 1, 2, 3
DIR_NAMES = {UP: "up", RIGHT: "right", DOWN: "down", LEFT: "left"}
NAME_TO_DIR = {v: k for k, v in DIR_NAMES.items()}


def _line_indices(direction, k):
    if direction == LEFT:
        return [k * 4, k * 4 + 1, k * 4 + 2, k * 4 + 3]
    if direction == RIGHT:
        return [k * 4 + 3, k * 4 + 2, k * 4 + 1, k * 4]
    if direction == UP:
        return [k, k + 4, k + 8, k + 12]
    return [k + 12, k + 8, k + 4, k]


def _slide(line):
    """Collapse one line toward index 0. Returns (new_line, score_gained)."""
    vals = [x for x in line if x]
    out, score, i = [], 0, 0
    while i < len(vals):
        if i + 1 < len(vals) and vals[i] == vals[i + 1]:
            out.append(vals[i] + 1)
            score += 1 << (vals[i] + 1)
            i += 2
        else:
            out.append(vals[i])
            i += 1
    while len(out) < 4:
        out.append(0)
    return out, score


def move(grid, direction):
    """Apply a move. Returns (new_grid, score_gained). Does not spawn a tile."""
    new = list(grid)
    score = 0
    for k in range(4):
        idx = _line_indices(direction, k)
        collapsed, gained = _slide([grid[i] for i in idx])
        for j, i in enumerate(idx):
            new[i] = collapsed[j]
        score += gained
    return new, score


def legal_moves(grid):
    """Directions that change the board. A move that is a no-op is illegal."""
    return [d for d in (UP, RIGHT, DOWN, LEFT) if move(grid, d)[0] != list(grid)]


def spawn(grid, rng):
    """Place one tile: 90% a 2 (exponent 1), 10% a 4 (exponent 2), uniform empty cell."""
    empty = [i for i, v in enumerate(grid) if v == 0]
    if not empty:
        return grid
    g = list(grid)
    g[rng.choice(empty)] = 1 if rng.random() < 0.9 else 2
    return g


def new_game(rng):
    g = [0] * 16
    g = spawn(g, rng)
    g = spawn(g, rng)
    return g


def game_rng(game_index):
    """Common random numbers: spawn sequence is a pure function of the game index, so
    every arm replays the same stochastic draws."""
    return random.Random(0xC0FFEE + game_index)


def max_tile(grid):
    return 1 << max(grid)


def render_rows(grid):
    """Raw tile values in a row-structured grid, zero derived features (Q11)."""
    rows = []
    for r in range(4):
        rows.append(" ".join(str(1 << v) if v else "." for v in grid[r * 4:r * 4 + 4]))
    return "\n".join(rows)
