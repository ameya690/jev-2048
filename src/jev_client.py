"""jev query construction and transport.

Verified request/response shape (probe_jev.py, 2026-10-18):

    POST https://openrouter.ai/api/v1/systemone      (OpenRouter passthrough)
    POST https://api.typesafe.ai/v1/systemone        (native, same body)
    {"model": ..., "state": "<text>",
     "questions": {"move": {"type": "choice", "instructions": ..., "criteria": {label: desc}}}}

    -> {"answers": {"move": {"choice": "left",
                             "probabilities": {"left": 0.45, "down": 0.3, "right": 0.25},
                             "confidence": 0.18}},
        "usage": {"input_tokens":441, "output_tokens":38, "cost":1.85e-05}}

The passthrough preserves `probabilities`, so the calibration work is possible through
either endpoint. jev's chat/completions route is rejected by design -- it is a decisions
model, not a text model.

Masking illegal moves (Q10) is free here: an illegal direction is simply omitted from
`criteria`, so jev is never offered it. Unmasked mode offers all four and exists only to
measure the illegal-move RATE, a separate question about whether jev grasps the mechanics.

Board rendering (Q11): raw tile values, row-structured, ZERO derived features.
"""
import json
import os
import random
import time
import urllib.error
import urllib.request

import board

OPENROUTER_URL = "https://openrouter.ai/api/v1/systemone"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"

RULES = (
    "2048 on a 4x4 grid. A move slides every tile as far as it can go in that direction; "
    "two tiles of equal value that collide merge into one tile of double the value. "
    "A move is only allowed if it changes the grid. After each move a new 2 or 4 appears "
    "in a random empty cell. The game ends when no move changes the grid."
)
OBJECTIVE = "Pick the move that leads to the highest final score."

DIR_DESCRIPTIONS = {
    "up": "Slide all tiles up.",
    "right": "Slide all tiles right.",
    "down": "Slide all tiles down.",
    "left": "Slide all tiles left.",
}


def load_key(paths=("~/.config/openrouter_key", "~/.config/typesafe_key")):
    for var in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    for p in paths:
        f = os.path.expanduser(p)
        # must be non-empty: a `printf "$UNSET_VAR" > file` leaves a 0-byte file behind
        if os.path.exists(f):
            k = open(f).read().strip()
            if k:
                return k
    raise RuntimeError("no API key found")


def endpoint_for(key):
    return (OPENROUTER_URL, "typesafe/jev-1.13") if key.startswith("sk-or-") else (TYPESAFE_URL, "jev-latest")


def render_state(grid, with_rules=True):
    parts = [RULES] if with_rules else []
    parts.append("Current grid:\n" + board.render_rows(grid))
    return "\n\n".join(parts)


def build_request(grid, model, with_rules=True, mask_illegal=True):
    dirs = board.legal_moves(grid) if mask_illegal else [board.UP, board.RIGHT, board.DOWN, board.LEFT]
    criteria = {board.DIR_NAMES[d]: DIR_DESCRIPTIONS[board.DIR_NAMES[d]] for d in dirs}
    return {
        "model": model,
        "state": render_state(grid, with_rules=with_rules),
        "questions": {"move": {"type": "choice", "instructions": OBJECTIVE, "criteria": criteria}},
    }, dirs


def parse_response(payload):
    """-> (chosen_dir, {dir: prob}, confidence, cost). chosen_dir is -1 if unparseable."""
    ans = (payload.get("answers") or {}).get("move") or {}
    chosen = board.NAME_TO_DIR.get(ans.get("choice"), -1)
    probs = {board.NAME_TO_DIR[k]: v for k, v in (ans.get("probabilities") or {}).items()
             if k in board.NAME_TO_DIR}
    return chosen, probs, ans.get("confidence"), (payload.get("usage") or {}).get("cost", 0.0)


def post(url, key, body, max_retries=6):
    """POST with exponential backoff on 429/529/5xx. Returns parsed JSON."""
    delay = 1.0
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (408, 429, 500, 502, 503, 529) and attempt < max_retries - 1:
                time.sleep(delay + random.random() * 0.5)
                delay = min(delay * 2, 30)
                continue
            raise RuntimeError("HTTP %d: %s" % (e.code, e.read().decode()[:300]))
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(delay + random.random() * 0.5)
                delay = min(delay * 2, 30)
                continue
            raise
    raise RuntimeError("exhausted retries")


def query_move(key, url, model, grid, with_rules=True, mask_illegal=True):
    body, dirs = build_request(grid, model, with_rules=with_rules, mask_illegal=mask_illegal)
    if not dirs:
        return -1, {}, None, 0.0, None
    payload = post(url, key, body)
    chosen, probs, conf, cost = parse_response(payload)
    return chosen, probs, conf, cost, payload
