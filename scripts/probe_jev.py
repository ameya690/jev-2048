"""ONE call to jev, dumping the raw response, to learn what the transport preserves.

The native TypeSafe endpoint returns `probabilities` per choice. Whether OpenRouter's
passthrough preserves that field decides which arms are runnable:
  Arm 1 (policy)            -- needs only the chosen label. Fine either way.
  Arm 3 (bucket evaluator)  -- needs the distribution to compute E[value]. Dead without.
  the calibration claim     -- needs the distribution. Dead without.

Tries the TypeSafe-native body first, then OpenAI-style tool calling, and prints whatever
comes back verbatim. Reads the key from a file or the environment; never prints it.

    python3 scripts/probe_jev.py [path-to-key-file]
"""
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import board  # noqa: E402
import jev_client  # noqa: E402


def load_key():
    if len(sys.argv) > 1 and os.path.exists(os.path.expanduser(sys.argv[1])):
        return open(os.path.expanduser(sys.argv[1])).read().strip()
    for var in ("OPENROUTER_API_KEY", "TYPESAFE_API_KEY"):
        if os.environ.get(var, "").strip():
            return os.environ[var].strip()
    for path in ("~/.config/openrouter_key", "~/.openrouter_key", "~/.config/typesafe_key"):
        f = os.path.expanduser(path)
        # must be non-empty: `!` shell state does not persist between commands, so a
        # `printf "$VAR" > file` with an unset VAR silently leaves a 0-byte file
        if os.path.exists(f) and open(f).read().strip():
            return open(f).read().strip()
    sys.exit("no key found: pass a file path, or write one to ~/.config/openrouter_key")


def post(url, body, key, extra=None):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers=dict({"Authorization": "Bearer " + key,
                      "Content-Type": "application/json"}, **(extra or {})),
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, "transport error: %r" % (e,)


GRID = [1, 2, 3, 0, 0, 1, 2, 0, 0, 0, 1, 0, 0, 0, 0, 0]
state = jev_client.render_state(GRID)
legal = [board.DIR_NAMES[d] for d in board.legal_moves(GRID)]
print("board:\n%s\nlegal: %s\n" % (board.render_rows(GRID), legal))

key = load_key()
is_or = key.startswith("sk-or-")
print("key source: %s\n" % ("OpenRouter" if is_or else "TypeSafe (native)"))

criteria = {d: jev_client.DIR_DESCRIPTIONS[d] for d in legal}

attempts = []
if is_or:
    attempts.append(("OpenRouter /systemone passthrough",
                     "https://openrouter.ai/api/v1/systemone",
                     {"model": "typesafe/jev-1.13", "state": state,
                      "questions": {"move": {"type": "choice",
                                             "instructions": jev_client.OBJECTIVE,
                                             "criteria": criteria}}}))
    attempts.append(("OpenRouter chat/completions + tool",
                     "https://openrouter.ai/api/v1/chat/completions",
                     {"model": "typesafe/jev-1.13",
                      "messages": [{"role": "user", "content": state + "\n\n" + jev_client.OBJECTIVE}],
                      "tools": [{"type": "function", "function": {
                          "name": "pick_move", "description": jev_client.OBJECTIVE,
                          "parameters": {"type": "object", "properties": {
                              "move": {"type": "string", "enum": legal}}, "required": ["move"]}}}],
                      "tool_choice": {"type": "function", "function": {"name": "pick_move"}}}))
else:
    attempts.append(("TypeSafe native /v1/systemone",
                     "https://api.typesafe.ai/v1/systemone",
                     {"model": "jev-latest", "state": state,
                      "questions": {"move": {"type": "choice",
                                             "instructions": jev_client.OBJECTIVE,
                                             "criteria": criteria}}}))

for name, url, body in attempts:
    print("=" * 70)
    print(name, "->", url)
    status, text = post(url, body, key)
    print("HTTP", status)
    try:
        print(json.dumps(json.loads(text), indent=2)[:2500])
    except Exception:
        print(text[:1500])
    print()
