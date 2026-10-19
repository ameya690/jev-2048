// 2048 expectimax engine. Board = 4 rows, each a 16-bit key of four 4-bit exponents
// (nibble i = column i, 0 = empty). Runs inside a Web Worker or under Node for tests.
const ROW_LEFT = new Uint16Array(65536);
const ROW_RIGHT = new Uint16Array(65536);
const HEUR = new Float64Array(65536);

let W = { lost: 200000, empty: 270, merges: 700, mono: 47, monoPow: 4, sum: 11, sumPow: 3.5 };

function buildMoveTables() {
  const line = [0, 0, 0, 0];
  for (let r = 0; r < 65536; r++) {
    line[0] = r & 15; line[1] = (r >> 4) & 15; line[2] = (r >> 8) & 15; line[3] = (r >> 12) & 15;
    for (let i = 0; i < 3; i++) {
      let j = i + 1;
      while (j < 4 && line[j] === 0) j++;
      if (j === 4) break;
      if (line[i] === 0) { line[i] = line[j]; line[j] = 0; i--; }
      else if (line[i] === line[j]) { if (line[i] !== 15) line[i]++; line[j] = 0; }
    }
    ROW_LEFT[r] = line[0] | (line[1] << 4) | (line[2] << 8) | (line[3] << 12);
  }
  for (let r = 0; r < 65536; r++) ROW_RIGHT[r] = reverseRow(ROW_LEFT[reverseRow(r)]);
}

function reverseRow(r) {
  return ((r & 15) << 12) | (((r >> 4) & 15) << 8) | (((r >> 8) & 15) << 4) | ((r >> 12) & 15);
}

function buildHeuristic(weights) {
  if (weights) W = Object.assign({}, W, weights);
  const pm = new Float64Array(16), ps = new Float64Array(16);
  for (let k = 0; k < 16; k++) { pm[k] = Math.pow(k, W.monoPow); ps[k] = Math.pow(k, W.sumPow); }
  for (let r = 0; r < 65536; r++) {
    const a = r & 15, b = (r >> 4) & 15, c = (r >> 8) & 15, d = (r >> 12) & 15;
    const line = [a, b, c, d];
    let sum = 0, empty = 0, merges = 0, prev = 0, counter = 0;
    for (let i = 0; i < 4; i++) {
      const rank = line[i];
      sum += ps[rank];
      if (rank === 0) empty++;
      else {
        if (prev === rank) counter++;
        else if (counter > 0) { merges += 1 + counter; counter = 0; }
        prev = rank;
      }
    }
    if (counter > 0) merges += 1 + counter;
    let monoL = 0, monoR = 0;
    for (let i = 1; i < 4; i++) {
      if (line[i - 1] > line[i]) monoL += pm[line[i - 1]] - pm[line[i]];
      else monoR += pm[line[i]] - pm[line[i - 1]];
    }
    HEUR[r] = W.lost + W.empty * empty + W.merges * merges - W.mono * Math.min(monoL, monoR) - W.sum * sum;
  }
}

// Transpose writes columns into T0..T3 (column key nibble i = row i).
let T0 = 0, T1 = 0, T2 = 0, T3 = 0;
function transpose(r0, r1, r2, r3) {
  T0 = (r0 & 15) | ((r1 & 15) << 4) | ((r2 & 15) << 8) | ((r3 & 15) << 12);
  T1 = ((r0 >> 4) & 15) | (((r1 >> 4) & 15) << 4) | (((r2 >> 4) & 15) << 8) | (((r3 >> 4) & 15) << 12);
  T2 = ((r0 >> 8) & 15) | (((r1 >> 8) & 15) << 4) | (((r2 >> 8) & 15) << 8) | (((r3 >> 8) & 15) << 12);
  T3 = ((r0 >> 12) & 15) | (((r1 >> 12) & 15) << 4) | (((r2 >> 12) & 15) << 8) | (((r3 >> 12) & 15) << 12);
}

// Directions: 0 up, 1 right, 2 down, 3 left. Result rows in M0..M3; returns true if the board changed.
let M0 = 0, M1 = 0, M2 = 0, M3 = 0;
function doMove(r0, r1, r2, r3, dir) {
  if (dir === 3 || dir === 1) {
    const t = dir === 3 ? ROW_LEFT : ROW_RIGHT;
    M0 = t[r0]; M1 = t[r1]; M2 = t[r2]; M3 = t[r3];
  } else {
    transpose(r0, r1, r2, r3);
    const t = dir === 0 ? ROW_LEFT : ROW_RIGHT;
    const c0 = t[T0], c1 = t[T1], c2 = t[T2], c3 = t[T3];
    transpose(c0, c1, c2, c3);
    M0 = T0; M1 = T1; M2 = T2; M3 = T3;
  }
  return M0 !== r0 || M1 !== r1 || M2 !== r2 || M3 !== r3;
}

function heur(r0, r1, r2, r3) {
  transpose(r0, r1, r2, r3);
  return HEUR[r0] + HEUR[r1] + HEUR[r2] + HEUR[r3] + HEUR[T0] + HEUR[T1] + HEUR[T2] + HEUR[T3];
}

function countEmpty(r) {
  return ((r & 15) === 0) + (((r >> 4) & 15) === 0) + (((r >> 8) & 15) === 0) + (((r >> 12) & 15) === 0);
}

function distinctTiles(r0, r1, r2, r3) {
  let mask = 0;
  for (const r of [r0, r1, r2, r3]) for (let i = 0; i < 16; i += 4) mask |= 1 << ((r >> i) & 15);
  mask >>= 1;
  let n = 0;
  while (mask) { n += mask & 1; mask >>= 1; }
  return n;
}

// Transposition table: open addressing keyed on two 32-bit halves, invalidated by generation.
const TT_BITS = 20, TT_SIZE = 1 << TT_BITS, TT_MASK = TT_SIZE - 1;
const ttA = new Int32Array(TT_SIZE), ttB = new Int32Array(TT_SIZE);
const ttGen = new Uint32Array(TT_SIZE), ttDepth = new Uint8Array(TT_SIZE), ttVal = new Float64Array(TT_SIZE);
let gen = 0;

const CPROB_MIN = 0.0001;
let depthLimit = 3, curDepth = 0, nodes = 0, maxReached = 0;

function chanceNode(r0, r1, r2, r3, cprob) {
  if (cprob < CPROB_MIN || curDepth >= depthLimit) {
    if (curDepth > maxReached) maxReached = curDepth;
    return heur(r0, r1, r2, r3);
  }
  const A = (r0 << 16) | r1, B = (r2 << 16) | r3;
  let h = (Math.imul(A, 0x9e3779b1) ^ Math.imul(B ^ (A >>> 15), 0x85ebca77)) >>> (32 - TT_BITS);
  for (let probe = 0; probe < 4; probe++) {
    const s = (h + probe) & TT_MASK;
    if (ttGen[s] === gen && ttA[s] === A && ttB[s] === B) {
      if (ttDepth[s] <= curDepth) return ttVal[s];
      break;
    }
  }
  const empty = countEmpty(r0) + countEmpty(r1) + countEmpty(r2) + countEmpty(r3);
  cprob /= empty;
  let res = 0;
  const rows = [r0, r1, r2, r3];
  for (let i = 0; i < 4; i++) {
    const row = rows[i];
    for (let s = 0; s < 16; s += 4) {
      if (((row >> s) & 15) !== 0) continue;
      rows[i] = row | (1 << s);
      res += maxNode(rows[0], rows[1], rows[2], rows[3], cprob * 0.9) * 0.9;
      rows[i] = row | (2 << s);
      res += maxNode(rows[0], rows[1], rows[2], rows[3], cprob * 0.1) * 0.1;
      rows[i] = row;
    }
  }
  res /= empty;
  // Store, replacing the first stale or matching slot (or the home slot).
  let slot = h & TT_MASK;
  for (let probe = 0; probe < 4; probe++) {
    const s = (h + probe) & TT_MASK;
    if (ttGen[s] !== gen || (ttA[s] === A && ttB[s] === B)) { slot = s; break; }
  }
  ttGen[slot] = gen; ttA[slot] = A; ttB[slot] = B; ttDepth[slot] = curDepth; ttVal[slot] = res;
  return res;
}

function maxNode(r0, r1, r2, r3, cprob) {
  nodes++;
  let best = 0;
  curDepth++;
  for (let dir = 0; dir < 4; dir++) {
    if (doMove(r0, r1, r2, r3, dir)) {
      const v = chanceNode(M0, M1, M2, M3, cprob);
      if (v > best) best = v;
    }
  }
  curDepth--;
  return best;
}

// grid: 16 exponents, row-major. Returns per-direction expected values (null = illegal).
function analyze(grid, maxDepth) {
  const rows = [0, 0, 0, 0];
  for (let i = 0; i < 16; i++) rows[i >> 2] |= Math.min(grid[i], 15) << ((i & 3) * 4);
  const [r0, r1, r2, r3] = rows;
  const t0 = Date.now();
  gen = (gen + 1) >>> 0 || 1;
  nodes = 0; maxReached = 0;
  depthLimit = Math.max(2, Math.min(maxDepth, distinctTiles(r0, r1, r2, r3) - 2));
  const scores = [null, null, null, null];
  let best = -1, bestVal = -Infinity;
  for (let dir = 0; dir < 4; dir++) {
    if (!doMove(r0, r1, r2, r3, dir)) continue;
    curDepth = 0;
    const v = chanceNode(M0, M1, M2, M3, 1);
    scores[dir] = v;
    if (v > bestVal) { bestVal = v; best = dir; }
  }
  return { best, scores, nodes, depth: depthLimit, ms: Date.now() - t0 };
}

buildMoveTables();
buildHeuristic();

if (typeof module !== 'undefined') module.exports = { analyze, buildHeuristic };
else {
  self.onmessage = (e) => {
    const m = e.data;
    if (m.type === 'weights') buildHeuristic(m.weights);
    else if (m.type === 'analyze') self.postMessage(Object.assign({ id: m.id }, analyze(m.grid, m.maxDepth)));
  };
}
