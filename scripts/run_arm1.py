"""Arm 1: jev as a policy, scored on the oracle-rollout position set.

This is the arm MEMO.md's kill criterion is written against. If jev's mean normalised
regret is not clearly better than legal-conditional random -- paired 95% CI on the
difference excluding zero -- stop, and Arms 2-5 are cancelled.

Concurrency is capped at 6: TypeSafe's cookbooks note the public endpoint rate-limits
above roughly eight, and the SDK handles 429/529 backoff internally.

    python3 scripts/run_arm1.py                  # the real thing, needs TYPESAFE_API_KEY
    python3 scripts/run_arm1.py --mock heuristic # pipeline check, no API calls

Mock mode substitutes a local agent for jev so the whole scoring path -- regret, strata,
clustered CIs, kill criterion -- can be validated before spending calls. It also tests
the criterion itself: --mock oracle must PASS with ~0 regret, --mock random must FAIL.
A criterion that cannot fail a worthless agent is not a criterion.
"""
import json
import os
import random
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "src"))
import baselines  # noqa: E402
import board  # noqa: E402
import jev_client  # noqa: E402
import metrics  # noqa: E402
import oracle  # noqa: E402
import strata  # noqa: E402

MAX_WORKERS = 6
REFERENCE = "d5_default"
POS_FILE = os.path.join(HERE, "data", "oracle_rollout.jsonl")
REF_FILE = os.path.join(HERE, "data", "reference_scores.jsonl")


def load_reference(positions):
    """Reference oracle EVs, shared with self_agreement.py via the same cache file."""
    if os.path.exists(REF_FILE):
        rows = [json.loads(l) for l in open(REF_FILE)]
        # >= not ==: positions may be a prefix slice (--limit). Treating a longer cache as
        # a miss recomputes AND overwrites it, which is how a smoke run can destroy the
        # full cache it was supposed to reuse.
        if len(rows) >= len(positions):
            return rows[:len(positions)]
    rows = []
    tmp = REF_FILE + ".tmp"
    with oracle.Oracle.from_config(REFERENCE) as orc, open(tmp, "w") as fh:
        for i, p in enumerate(positions):
            r = orc.analyze(p["grid"])
            rows.append({"best": r["best"], "scores": r["scores"]})
            fh.write(json.dumps(rows[-1]) + "\n")
            if i and i % 2500 == 0:
                print("  reference %d/%d" % (i, len(positions)), flush=True)
    os.replace(tmp, REF_FILE)
    return rows


RAW_FILE = os.path.join(HERE, "data", "jev_arm1_raw.jsonl")


def moves_from_jev(positions):
    """Query jev for every position, persisting raw responses as they land.

    Raw responses are kept so the calibration analysis (do the probabilities carry
    information beyond their ranking?) costs nothing later -- re-deriving it must never
    require re-calling. The file also makes the run resumable: a rate-limit stall or a
    killed process resumes from the last completed index instead of paying again.
    """
    key = jev_client.load_key()
    url, model = jev_client.endpoint_for(key)
    print("endpoint %s  model %s" % (url, model))

    done = {}
    if os.path.exists(RAW_FILE):
        for line in open(RAW_FILE):
            try:
                r = json.loads(line)
                done[r["i"]] = r
            except Exception:
                pass
        if done:
            print("resuming: %d/%d already answered" % (len(done), len(positions)))

    todo = [i for i in range(len(positions)) if i not in done]
    t0 = time.time()
    if todo:
        lock = threading.Lock()
        fh = open(RAW_FILE, "a")

        def ask(i):
            d, probs, conf, cost, _payload = jev_client.query_move(key, url, model, positions[i]["grid"])
            rec = {"i": i, "choice": d, "probs": {str(k): v for k, v in probs.items()},
                   "confidence": conf, "cost": cost}
            with lock:
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                done[i] = rec
                n = len(done)
                if n % 500 == 0:
                    el = time.time() - t0
                    print("  %d/%d  %.1f/s  $%.4f" % (n, len(positions), (n - (len(positions) - len(todo))) / max(el, 1e-9),
                                                      sum(r.get("cost") or 0 for r in done.values())), flush=True)
            return rec

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            list(pool.map(ask, todo))
        fh.close()

    dt = time.time() - t0
    spent = sum(r.get("cost") or 0 for r in done.values())
    print("jev: %d calls, %d new in %.0fs (%.1f/s, %d workers), total $%.4f"
          % (len(positions), len(todo), dt, len(todo) / max(dt, 1e-9), MAX_WORKERS, spent))
    return [(done[i]["choice"], {int(k): v for k, v in done[i]["probs"].items()}) for i in range(len(positions))]


def moves_from_mock(positions, kind, ref):
    rng = random.Random(777)
    out = []
    for p, r in zip(positions, ref):
        if kind == "oracle":
            d = r["best"]
        elif kind == "heuristic":
            d = baselines.heuristic_agent(p["grid"])
        elif kind == "random":
            d = baselines.legal_conditional_random(p["grid"], rng)
        else:
            sys.exit("unknown mock agent: %s" % kind)
        out.append((d, {}))
    return out


def main():
    mock = None
    if "--mock" in sys.argv:
        mock = sys.argv[sys.argv.index("--mock") + 1]
    label = "jev" if not mock else "MOCK:" + mock

    positions = [json.loads(l) for l in open(POS_FILE)]
    if "--limit" in sys.argv:
        n = int(sys.argv[sys.argv.index("--limit") + 1])
        positions = positions[:n]
        print("LIMITED to first %d positions (smoke run)" % n)
    gids = [p["game"] for p in positions]
    print("positions: %d from %d games   agent under test: %s" % (len(positions), len(set(gids)), label))
    ref = load_reference(positions)

    floor = metrics.choose_spread_floor([metrics.spread(r["scores"]) for r in ref], quantile=0.25)
    print("spread floor: %.6g\n" % floor)

    out = moves_from_mock(positions, mock, ref) if mock else moves_from_jev(positions)

    rng = random.Random(1234)
    agent_r, rand_r, heur_r = [], [], []
    rand_moves, heur_moves = [], []
    for p, r, (chosen, _probs) in zip(positions, ref, out):
        rm = baselines.legal_conditional_random(p["grid"], rng)
        hm = baselines.heuristic_agent(p["grid"])
        rand_moves.append(rm)
        heur_moves.append(hm)
        agent_r.append(metrics.normalized_regret(r["scores"], chosen, floor))
        rand_r.append(metrics.normalized_regret(r["scores"], rm, floor))
        heur_r.append(metrics.normalized_regret(r["scores"], hm, floor))

    # Top-1 agreement with the oracle, over gradeable positions only. Secondary to regret
    # because it weights every position equally -- a near-tied board where disagreement
    # costs nothing counts the same as a critical one. Reported because it is legible, and
    # because the gap between it and regret is itself informative: high accuracy with low
    # regret means the misses are cheap, low accuracy with low regret means they are cheap
    # AND frequent.
    def accuracy(moves):
        hits = tot = 0
        for r, d, gr in zip(ref, moves, agent_r):
            if gr is None:   # ungradeable: no decision, or below the spread floor
                continue
            tot += 1
            hits += 1 if d == r["best"] else 0
        return hits / tot if tot else float("nan")

    acc = {label: accuracy([c for c, _ in out]),
           "legal-conditional random": accuracy(rand_moves),
           "hand heuristic": accuracy(heur_moves)}

    report = {"agent": label, "n_positions": len(positions), "spread_floor": floor, "overall": {}, "strata": {}}
    moves_by = {label: [c for c, _ in out], "legal-conditional random": rand_moves, "hand heuristic": heur_moves}
    perpos = {label: agent_r, "legal-conditional random": rand_r, "hand heuristic": heur_r}
    print("PRIMARY: spread-weighted regret = total EV forfeited / total EV available (no floor)")
    print("%-28s %8s  %-24s %9s %9s" % ("agent", "regret", "95% CI (clustered by game)", "per-pos", "top-1"))
    for name in (label, "legal-conditional random", "hand heuristic"):
        m, lo, hi, ng = metrics.spread_weighted_regret(ref, moves_by[name], gids)
        pp = metrics.clustered_mean_ci(perpos[name], gids)[0]
        print("%-28s %8.4f  [%.4f, %.4f]  n=%-3d %8.4f %8.1f%%" % (name, m, lo, hi, ng, pp, 100 * acc[name]))
        report["overall"][name] = {"spread_weighted": m, "lo": lo, "hi": hi, "n_games": ng,
                                   "per_position_floored": pp, "top1": acc[name]}

    dm, dlo, dhi, ndiff = metrics.paired_spread_weighted(ref, [c for c, _ in out], rand_moves, gids)
    undecidable = ndiff < 2 or dhi != dhi  # NaN CI: too few game clusters to test
    passed = (not undecidable) and dhi < 0
    print("\nPAIRED %s - random : %+.4f  [%+.4f, %+.4f]" % (label, dm, dlo, dhi))
    if undecidable:
        verdict_txt = "INSUFFICIENT DATA - %d game cluster(s); need >=2 for a CI" % ndiff
    elif passed:
        verdict_txt = "PASS - beats random, Arm 2 is justified"
    else:
        verdict_txt = "FAIL - stop here, do not build Arms 2-5"
    print("KILL CRITERION: %s" % verdict_txt)
    report["kill_criterion"] = {"paired_minus_random": dm, "lo": dlo, "hi": dhi,
                                "passed": bool(passed), "undecidable": bool(undecidable)}

    dm2, dlo2, dhi2, _ = metrics.paired_spread_weighted(ref, [c for c, _ in out], heur_moves, gids)
    verdict = "beats heuristic" if dhi2 < 0 else ("loses to heuristic" if dlo2 > 0 else "indistinguishable from heuristic")
    print("PAIRED %s - heuristic : %+.4f  [%+.4f, %+.4f]  -> %s" % (label, dm2, dlo2, dhi2, verdict))
    report["vs_heuristic"] = {"mean": dm2, "lo": dlo2, "hi": dhi2, "verdict": verdict}

    print("\nBy game stage:")
    print("%-10s %7s %9s %9s %9s" % ("stratum", "n", label[:9], "random", "heurstc"))
    groups = strata.group(positions)
    for _, _, name in strata.STRATA:
        ii = groups[name]
        if not ii:
            continue
        g = [gids[i] for i in ii]
        sub_ref = [ref[i] for i in ii]
        a = metrics.spread_weighted_regret(sub_ref, [moves_by[label][i] for i in ii], g)[0]
        b = metrics.spread_weighted_regret(sub_ref, [rand_moves[i] for i in ii], g)[0]
        c = metrics.spread_weighted_regret(sub_ref, [heur_moves[i] for i in ii], g)[0]
        mark = "  <- live regime" if name in strata.LIVE else ""
        print("%-10s %7d %9.4f %9.4f %9.4f%s" % (name, len(ii), a, b, c, mark))
        report["strata"][name] = {"n": len(ii), "agent": a, "random": b, "heuristic": c}

    out_path = os.path.join(HERE, "results", "arm1_%s.json" % (mock or "jev"))
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=2)
    print("\nwrote %s" % out_path)


if __name__ == "__main__":
    main()
