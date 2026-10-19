# Expectimax 2048

An expectimax search that plays 2048 in your browser. It rates all four moves by averaging over every possible tile spawn, and scores positions with a weighted heuristic you can tune with sliders.

**Live site:** https://andyqueyl.github.io/expectimax-2048/

- **Watch it play** at five speeds and search depths 2 to 6. The panel shows each move's expected value, positions searched and search speed.
- **Tune the heuristic**: empty cells, merges, monotonicity, tile sum, plus four presets. Every finished game is logged with the weights and depth it used, so you can compare settings.
- **Play yourself** with arrow keys, WASD or swipes. The solver keeps showing its recommended move.

## How it works

Each row of the board is a 16-bit number made of four 4-bit tile exponents. Lookup tables precompute the result of sliding every possible row and the heuristic score of every row, so a move or evaluation is just a few table reads. The search runs in a Web Worker with a transposition table, and it prunes branches whose spawn probability falls below 0.0001.

In Node test games, depth 3 reached 2048 in 6 of 6 games and 8192 in 3 of 6. Depth 5 reached 8192 in 3 of 3 and 16384 in 2 of 3, at about 35 ms per move.

## Files

- `index.html` is the whole site. The engine is inlined into it and started as a Worker.
- `engine/engine.js` is the same engine as a Node module, and `engine/test.js` plays full games with it:

```sh
node engine/test.js 4 5   # depth 4, 5 games
```

If you change the engine, copy it into the `engine-src` script block in `index.html` as well. Scores and settings are stored only in your browser.
