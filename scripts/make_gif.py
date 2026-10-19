"""Render one of Jev's games as an animated GIF for the README.

Each frame is a board plus the move Jev chose and what the engine thought of it, so the
clip shows the decisions rather than just the tiles moving. Frames are subsampled: a
272-ply game at every ply would be a minute long and several megabytes.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(HERE, "docs")
GAME = int(sys.argv[1]) if len(sys.argv) > 1 else 3
STEP = int(sys.argv[2]) if len(sys.argv) > 2 else 3

BG, FRAME, CELL = "#faf8f4", "#b9aa9c", "#cdc0b4"
INK, DIM, FAINT = "#23211e", "#6e675e", "#9c948a"
GOOD, INACC, MIST, BLUN = "#41762f", "#1a6fa8", "#cf8f08", "#a8271d"
TILE = {2: "#eee4da", 4: "#ede0c8", 8: "#f2b179", 16: "#f59563", 32: "#f67c5f",
        64: "#f65e3b", 128: "#edcf72", 256: "#edcc61", 512: "#edc850",
        1024: "#edc53f", 2048: "#edc22e"}
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def f(p, s):
    try:
        return ImageFont.truetype(p, s)
    except Exception:
        return ImageFont.load_default()


W, H = 360, 500
PAD, GAP = 14, 8
CELLSZ = (W - 2 * PAD - 5 * GAP) // 4
TOP = 92

big = f(BOLD, 15)
sm = f(SANS, 12)
tiny = f(SANS, 11)
tilefonts = {n: f(BOLD, 30 if n < 100 else (26 if n < 1000 else 21)) for n in TILE}
ARROWS = {0: "UP", 1: "RIGHT", 2: "DOWN", 3: "LEFT"}


def grade(p):
    r = p["regret"] or 0
    if p["choice"] == p["oracle_best"]:
        return "engine move", GOOD
    if r >= .30:
        return "?? blunder", BLUN
    if r >= .20:
        return "? mistake", MIST
    if r >= .10:
        return "?! inaccuracy", INACC
    return "playable", DIM


def frame(p, i, n, final=False):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((PAD, 14), "JEV 1.13 PLAYS 2048", font=big, fill=INK)
    d.text((PAD, 36), "game %d · move %d of %d · score %s"
           % (GAME, i + 1, n, format(p["score"], ",")), font=sm, fill=DIM)
    lab, col = grade(p)
    if not final:
        d.text((PAD, 60), ARROWS[p["choice"]], font=big, fill=INK)
        d.text((PAD + 62, 62), lab, font=sm, fill=col)
        if p["regret"]:
            d.text((W - PAD, 62), "-%d%% value" % round(100 * p["regret"]),
                   font=sm, fill=col, anchor="ra")
    else:
        d.text((PAD, 60), "GAME OVER", font=big, fill=BLUN)

    d.rectangle([PAD, TOP, W - PAD, TOP + (W - 2 * PAD)], fill=FRAME)
    for idx, e in enumerate(p["grid"]):
        r, c = idx // 4, idx % 4
        x = PAD + GAP + c * (CELLSZ + GAP)
        y = TOP + GAP + r * (CELLSZ + GAP)
        v = (1 << e) if e else 0
        d.rectangle([x, y, x + CELLSZ, y + CELLSZ], fill=TILE.get(v, CELL) if v else CELL)
        if v:
            d.text((x + CELLSZ / 2, y + CELLSZ / 2), str(v),
                   font=tilefonts.get(v, tiny),
                   fill="#776e65" if v < 8 else "#f9f6f2", anchor="mm")

    by = TOP + (W - 2 * PAD) + 16
    d.text((PAD, by), "engine's preferred move", font=tiny, fill=FAINT)
    sc = p["oracle_scores"]
    vals = [s for s in sc if s is not None]
    hi, lo = max(vals), min(vals)
    bw = (W - 2 * PAD - 3 * 6) / 4
    for k in range(4):
        x = PAD + k * (bw + 6)
        y = by + 18
        share = 0 if sc[k] is None else ((sc[k] - lo) / (hi - lo) if hi > lo else 1)
        d.rectangle([x, y, x + bw, y + 9], fill="#e4ded4")
        if sc[k] is not None:
            fill = GOOD if k == p["oracle_best"] else "#bdb5a8"
            d.rectangle([x, y, x + bw * share, y + 9], fill=fill)
        d.text((x + bw / 2, y + 14), ARROWS[k][0] if sc[k] is not None else "×",
               font=tiny, fill=INK if k == p["choice"] else FAINT, anchor="ma")
        if k == p["choice"]:
            d.rectangle([x - 1, y - 3, x + bw + 1, y + 12], outline=col, width=2)
    return im


games = {json.loads(l)["game"]: json.loads(l) for l in open(os.path.join(HERE, "data", "jev_games.jsonl"))}
g = games[GAME]
plies = g["plies"]
idxs = list(range(0, len(plies), STEP))
if idxs[-1] != len(plies) - 1:
    idxs.append(len(plies) - 1)

frames = [frame(plies[i], i, len(plies)) for i in idxs]
last = dict(plies[-1])
last["grid"] = g["final_grid"]
last["score"] = g["final_score"]
frames += [frame(last, len(plies) - 1, len(plies), final=True)] * 8

out = os.path.join(DOCS, "jev_game%d.gif" % GAME)
frames[0].save(out, save_all=True, append_images=frames[1:], duration=140, loop=0,
               optimize=True, disposal=2)
print("wrote %s — %d frames, %.1f MB, %d plies sampled every %d"
      % (out, len(frames), os.path.getsize(out) / 1e6, len(plies), STEP))
