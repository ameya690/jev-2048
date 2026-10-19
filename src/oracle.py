"""Python driver for the JS expectimax oracle.

One subprocess per oracle CONFIG (depth + heuristic weights). Weights are fixed at
startup because buildHeuristic() rebuilds a 65536-entry table.

The engine returns expected values in HEURISTIC units, not game score: the baseline is
~1.6e6 and the spread between moves is often <1e-6. Absolute EVs are meaningless and
relative-to-best normalisation is useless; only (best - chosen)/(best - worst) with a
spread threshold carries signal. See metrics.py.
"""
import json
import os
import subprocess

ORACLE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "oracle")

# Two genuinely different value functions, not just two depths. The engine clamps
# depth to distinctTiles-2, so depth 3 and depth 5 are IDENTICAL on early boards;
# varying the heuristic is the only way to probe the ceiling across the whole game.
CONFIGS = {
    "d5_default": {"depth": 5, "weights": None},
    "d3_default": {"depth": 3, "weights": None},
    "d5_altweights": {"depth": 5, "weights": {"empty": 400, "merges": 300, "mono": 90, "sum": 4}},
}


class Oracle:
    def __init__(self, depth=5, weights=None):
        cmd = ["node", os.path.join(ORACLE_DIR, "server.js"), "--depth", str(depth)]
        if weights:
            cmd += ["--weights", json.dumps(weights)]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self._next_id = 0

    @classmethod
    def from_config(cls, name):
        cfg = CONFIGS[name]
        return cls(depth=cfg["depth"], weights=cfg["weights"])

    def analyze(self, grid):
        """Returns {'best': dir or -1, 'scores': [4 nullable floats], 'depth':, 'nodes':}."""
        req = {"id": self._next_id, "grid": list(grid)}
        self._next_id += 1
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("oracle process died")
        res = json.loads(line)
        assert res["id"] == req["id"], "oracle response out of order"
        return res

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
