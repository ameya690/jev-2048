"""Game-stage strata, shared by the ceiling measurement and every arm.

Granularity is set by where the action is. A no-search agent (measured: the hand
heuristic reaches 512 in 15/20 games, 1024 in 1/20, never 2048) lives at or below 512,
so the low end gets two buckets of its own. The high buckets hold most of the
oracle-rollout positions but describe boards no search-free agent ever creates.
"""
STRATA = [
    (0, 256, "<=256"),
    (257, 512, "512"),
    (513, 1024, "1024"),
    (1025, 2048, "2048"),
    (2049, 1 << 20, ">=4096"),
]
LIVE = {"<=256", "512"}  # the regime a search-free agent actually occupies


def label_for(max_tile):
    for lo, hi, name in STRATA:
        if lo <= max_tile <= hi:
            return name
    return ">=4096"


def group(positions):
    """{stratum label: [indices]} preserving STRATA order."""
    out = {name: [] for _, _, name in STRATA}
    for i, p in enumerate(positions):
        out[label_for(p["max_tile"])].append(i)
    return out
