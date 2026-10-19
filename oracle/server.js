// JSON-lines oracle server wrapping the vendored expectimax engine.
//
// Vendored from https://github.com/andyqueyl/expectimax-2048 @ b747f14 (MIT-style, see
// UPSTREAM_README.md). No patch was needed: analyze() already returns per-move expected
// values in `scores`, with null for illegal moves. That is exactly what regret needs.
//
//   in : {"id": 0, "grid": [16 exponents, row-major]}
//   out: {"id": 0, "best": dir, "scores": [4 nullable floats], "depth": d, "nodes": n}
//
// Directions: 0 up, 1 right, 2 down, 3 left.
//
// One process per oracle CONFIG (depth + heuristic weights). Weights are set once at
// startup rather than per-request, because buildHeuristic() rebuilds a 65536-entry
// lookup table and must not sit in the hot loop.
const readline = require('readline');
const { analyze, buildHeuristic } = require('./engine.js');

function argOf(flag, dflt) {
  const i = process.argv.indexOf(flag);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : dflt;
}

const maxDepth = parseInt(argOf('--depth', '5'), 10);
const weightsRaw = argOf('--weights', null);
if (weightsRaw) buildHeuristic(JSON.parse(weightsRaw));

// One line out per line in, flushed immediately. The rollout driver is sequential
// (analyze -> move -> spawn -> analyze), so any output buffering here deadlocks it.
const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on('line', (line) => {
  line = line.trim();
  if (!line) return;
  const req = JSON.parse(line);
  const r = analyze(req.grid, maxDepth);
  process.stdout.write(JSON.stringify({
    id: req.id, best: r.best, scores: r.scores, depth: r.depth, nodes: r.nodes,
  }) + '\n');
});
