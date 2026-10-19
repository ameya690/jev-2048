"""Render the README figures as PNGs.

Light ground throughout: GitHub serves one image to both its themes, so a mid-light
surface with dark ink is the only choice that stays legible in each. Status hues are the
light-surface steps validated in the project write-up, not the dark ones.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
DOCS = os.path.join(HERE, "docs")
S = 2  # supersample, downscaled at save for clean edges

BG, INK, DIM, FAINT, LINE = "#faf8f4", "#23211e", "#6e675e", "#9c948a", "#ddd7cc"
GOOD, INACC, MIST, BLUN = "#41762f", "#1a6fa8", "#cf8f08", "#a8271d"
ACCENT = "#8a6a4f"

SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/Menlo.ttc"


def f(path, size):
    try:
        return ImageFont.truetype(path, size * S)
    except Exception:
        return ImageFont.load_default()


def canvas(w, h):
    im = Image.new("RGB", (w * S, h * S), BG)
    return im, ImageDraw.Draw(im)


def save(im, name):
    im = im.resize((im.width // S, im.height // S), Image.LANCZOS)
    im.save(os.path.join(DOCS, name))
    print("wrote docs/%s  (%dx%d)" % (name, im.width, im.height))


def text(d, xy, s, font, fill=INK, anchor="la"):
    d.text((xy[0] * S, xy[1] * S), s, font=font, fill=fill, anchor=anchor)


def rect(d, box, fill=None, outline=None, width=1):
    d.rectangle([box[0] * S, box[1] * S, box[2] * S, box[3] * S],
                fill=fill, outline=outline, width=width * S)


# ---------------------------------------------------------------- figure 1
def fig_regret():
    rows = [("Expectimax oracle (ceiling)", 0.0015, 0.0012, 0.0019, DIM),
            ("Hand heuristic, 40 lines", 0.0111, 0.0086, 0.0136, GOOD),
            ("Jev 1.13, prose board", 0.0821, 0.0617, 0.1025, ACCENT),
            ("Jev 1.13, raw grid", 0.1222, 0.1013, 0.1432, MIST),
            ("Random among legal moves", 0.3039, 0.2885, 0.3193, BLUN)]
    W, H = 760, 330
    im, d = canvas(W, H)
    t, sm, mo = f(BOLD, 15), f(SANS, 11), f(MONO, 11)
    text(d, (24, 20), "Value forfeited per move, scored on identical boards", t)
    text(d, (24, 42), "Spread-weighted regret. 0 = matches the oracle, 1 = always the worst legal move.", sm, DIM)

    x0, x1 = 250, W - 92
    mx = 0.33
    for i, (lab, v, lo, hi, col) in enumerate(rows):
        y = 78 + i * 42
        text(d, (x0 - 12, y + 9), lab, sm, INK, anchor="ra")
        rect(d, (x0, y + 3, x1, y + 17), fill="#efece5")
        bw = (x1 - x0) * (v / mx)
        rect(d, (x0, y + 3, x0 + bw, y + 17), fill=col)
        lo_x, hi_x = x0 + (x1 - x0) * (lo / mx), x0 + (x1 - x0) * (hi / mx)
        d.line([lo_x * S, (y + 10) * S, hi_x * S, (y + 10) * S], fill=INK, width=1 * S)
        for xx in (lo_x, hi_x):
            d.line([xx * S, (y + 6) * S, xx * S, (y + 14) * S], fill=INK, width=1 * S)
        text(d, (x1 + 10, y + 9), "%.1f%%" % (100 * v), mo, INK)

    yb = 78 + len(rows) * 42 + 2
    d.line([x0 * S, yb * S, x1 * S, yb * S], fill=LINE, width=1 * S)
    for g in (0, .1, .2, .3):
        gx = x0 + (x1 - x0) * (g / mx)
        d.line([gx * S, yb * S, gx * S, (yb + 4) * S], fill=LINE, width=1 * S)
        text(d, (gx, yb + 8), "%d%%" % (100 * g), sm, FAINT, anchor="ma")
    text(d, (24, yb + 30), "Bars show the mean; whiskers are 95% CIs clustered by game (n=20).", sm, FAINT)
    save(im, "fig1_regret.png")


# ---------------------------------------------------------------- figure 2
def fig_onpolicy():
    pairs = [("Hand heuristic", 0.0111, 0.1432, GOOD),
             ("Jev 1.13", 0.0821, 0.3605, ACCENT),
             ("Random", 0.3039, 0.5243, BLUN)]
    W, H = 760, 300
    im, d = canvas(W, H)
    t, sm, mo, smb = f(BOLD, 15), f(SANS, 11), f(MONO, 11), f(BOLD, 11)
    text(d, (24, 20), "The same agent, scored on two different sets of boards", t)
    text(d, (24, 42), "Judging moves on a strong player's boards flatters every agent. Its own boards are the honest test.", sm, DIM)

    x0, x1 = 170, W - 150
    mx = 0.56
    for i, (lab, on, off, col) in enumerate(pairs):
        y = 86 + i * 58
        text(d, (x0 - 12, y + 14), lab, smb, INK, anchor="ra")
        for j, (v, alpha_fill, tag) in enumerate([(on, "#d9d4ca", "oracle's boards"), (off, col, "its own boards")]):
            yy = y + j * 16
            rect(d, (x0, yy, x0 + (x1 - x0) * (v / mx), yy + 12), fill=alpha_fill)
            text(d, (x1 + 10, yy + 6), "%.1f%%" % (100 * v), mo, INK if j else DIM)
            if i == 0:
                text(d, (x1 + 64, yy + 6), tag, sm, FAINT)
        mult = off / on
        text(d, (x0 + 6, y + 36), "%.1f× worse off-policy" % mult, sm, DIM)

    text(d, (24, H - 26), "Jev's errors compound: it degrades 4.4× once it has to live with the boards it creates.", sm, FAINT)
    save(im, "fig2_onpolicy.png")


# ---------------------------------------------------------------- figure 3
def fig_calibration():
    rep = json.load(open(os.path.join(HERE, "results", "calibration.json")))
    bins = [b for b in rep["bins"] if b["n"]]
    W, H = 460, 400
    im, d = canvas(W, H)
    t, sm, mo = f(BOLD, 15), f(SANS, 11), f(MONO, 10)
    text(d, (24, 20), "Is Jev's stated confidence real?", t)
    text(d, (24, 42), "Stated probability vs how often that move was in fact best.", sm, DIM)
    L, R, T, B = 92, W - 30, 72, H - 86
    rect(d, (L, T, R, B), outline=LINE, width=1)
    for g in (0, .25, .5, .75, 1.0):
        gx, gy = L + (R - L) * g, B - (B - T) * g
        d.line([L * S, gy * S, R * S, gy * S], fill="#efece5", width=1 * S)
        text(d, (L - 8, gy), "%d%%" % (100 * g), mo, FAINT, anchor="rm")
        text(d, (gx, B + 8), "%d%%" % (100 * g), mo, FAINT, anchor="ma")
    d.line([L * S, B * S, R * S, T * S], fill=FAINT, width=1 * S)
    text(d, (R - 6, T + 10), "perfect", sm, FAINT, anchor="ra")
    text(d, (26, (T + B) / 2), "actually best", sm, DIM, anchor="lm")
    pts = []
    for b in bins:
        px = L + (R - L) * b["stated"]
        py = B - (B - T) * b["actual"]
        pts.append((px, py, b["n"]))
    for i in range(len(pts) - 1):
        d.line([pts[i][0] * S, pts[i][1] * S, pts[i + 1][0] * S, pts[i + 1][1] * S], fill=ACCENT, width=2 * S)
    for px, py, n in pts:
        r = max(3, min(9, (n / 11516.0) ** .5 * 11))
        d.ellipse([(px - r) * S, (py - r) * S, (px + r) * S, (py + r) * S], fill=ACCENT, outline=BG, width=1 * S)
    text(d, (L, H - 40), "ECE %.3f — calibrated in form." % rep["ece"], sm, INK)
    text(d, (L, H - 24), "But its mass sits in 10–50%: it is rarely confident at all.", sm, DIM)
    save(im, "fig3_calibration.png")


# ---------------------------------------------------------------- figure 4
def fig_illegal():
    data = [(4, 0.0, 0.0, 1384), (3, 39.8, 25.0, 530), (2, 67.4, 50.0, 86)]
    W, H = 560, 290
    im, d = canvas(W, H)
    t, sm, mo, smb = f(BOLD, 15), f(SANS, 11), f(MONO, 11), f(BOLD, 11)
    text(d, (24, 20), "Jev picks illegal moves more often than chance", t)
    text(d, (24, 42), "All four directions offered. A move that cannot change the board is illegal.", sm, DIM)
    x0, x1 = 150, W - 108
    mx = 75.0
    for i, (nl, got, chance, n) in enumerate(data):
        y = 86 + i * 56
        text(d, (x0 - 12, y + 14), "%d legal moves" % nl, smb, INK, anchor="ra")
        text(d, (x0 - 12, y + 29), "n=%d" % n, sm, FAINT, anchor="ra")
        rect(d, (x0, y, x0 + (x1 - x0) * (chance / mx), y + 12), fill="#d9d4ca")
        text(d, (x1 + 10, y + 6), "%.0f%% chance" % chance, sm, DIM)
        rect(d, (x0, y + 16, x0 + (x1 - x0) * (got / mx), y + 28), fill=BLUN)
        text(d, (x1 + 10, y + 22), "%.1f%% jev" % got, mo, INK)
    text(d, (24, H - 26), "Not merely blind to legality — drawn to it: the illegal move usually points at the big tile.", sm, FAINT)
    save(im, "fig4_illegal.png")


# ---------------------------------------------------------------- figure 5
def fig_classes():
    games = [json.loads(l) for l in open(os.path.join(HERE, "data", "jev_games.jsonl"))]
    regs = [p["regret"] or 0 for g in games for p in g["plies"]]
    n = len(regs)
    cats = [("Blunder", sum(1 for r in regs if r >= .30), BLUN, "??"),
            ("Mistake", sum(1 for r in regs if .20 <= r < .30), MIST, "?"),
            ("Inaccuracy", sum(1 for r in regs if .10 <= r < .20), INACC, "?!"),
            ("Playable", sum(1 for r in regs if r < .10), GOOD, "")]
    W, H = 660, 190
    im, d = canvas(W, H)
    t, sm, mo, smb = f(BOLD, 15), f(SANS, 11), f(MONO, 12), f(BOLD, 11)
    text(d, (24, 20), "Every move Jev played, graded like a chess game", t)
    text(d, (24, 42), "Lichess thresholds: inaccuracy loses 10% of available value, mistake 20%, blunder 30%.", sm, DIM)
    x0, x1, y = 24, W - 24, 76
    cx = x0
    for lab, c, col, g in cats:
        w = (x1 - x0) * c / n
        rect(d, (cx, y, cx + w, y + 34), fill=col)
        if w > 44:
            text(d, (cx + w / 2, y + 17), "%.0f%%" % (100.0 * c / n), smb, "#ffffff", anchor="mm")
        cx += w
    lx = x0
    for lab, c, col, g in cats:
        rect(d, (lx, y + 48, lx + 10, y + 58), fill=col)
        text(d, (lx + 16, y + 47), ("%s %s" % (g, lab)).strip(), smb, INK)
        text(d, (lx + 16, y + 62), "%d moves" % c, mo, DIM)
        lx += 160
    text(d, (24, H - 22), "575 of 1,627 moves — 35% — are outright blunders.", sm, FAINT)
    save(im, "fig5_classes.png")


for fn in (fig_regret, fig_onpolicy, fig_calibration, fig_illegal, fig_classes):
    fn()
