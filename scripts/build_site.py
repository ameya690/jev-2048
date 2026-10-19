"""Build a standalone replay page for GitHub Pages from the artifact source.

The artifact platform wraps pages in its own document shell, so the source has no
<!doctype>, <html> or <head>. Self-hosting means supplying those, plus the small reset
that shell provided (color-scheme, zero body margin, responsive images).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1]
OUT = os.path.join(HERE, "docs", "index.html")

s = open(SRC, encoding="utf-8").read()
cut = s.index("</style>") + len("</style>")
head, body = s[:cut], s[cut:]

# Built by concatenation, not %-formatting: the reset CSS contains "100%}", which
# Python reads as an invalid format spec.
RESET = (
    "<style>\n"
    "  :root{color-scheme:light dark;padding-top:env(safe-area-inset-top,0px);"
    "padding-bottom:env(safe-area-inset-bottom,0px)}\n"
    "  body{margin:0}\n"
    "  img{max-width:100%}\n"
    "  [hidden]{display:none!important}\n"
    "</style>\n"
)
DESC = ("<meta name=\"description\" content=\"Ten 2048 games played move by move by "
        "TypeSafe's Jev classifier, analysed against a depth-5 expectimax engine.\">\n")

doc = ("<!doctype html>\n<html lang=\"en\">\n<head>\n"
       "<meta charset=\"utf-8\">\n"
       "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
       + DESC + RESET + head + "\n</head>\n<body>\n" + body.strip() + "\n</body>\n</html>\n")

open(OUT, "w", encoding="utf-8").write(doc)
print("wrote docs/index.html  (%.0f KB)" % (len(doc) / 1024))
