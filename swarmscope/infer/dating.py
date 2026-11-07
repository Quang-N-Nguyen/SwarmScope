"""When did an undated event happen? Anchor propagation on the evidence graph.

Plain steps:

1. **Anchors** are events with a date read from the data (a unix time or an
   ISO date inside the incident window), plus decoded layers that inherit
   their payload's date.
2. An undated event looks at linked neighbours that have a time and takes the
   **weighted median** of their times. The median ignores a single odd
   neighbour, which a mean would not.
3. Two rounds, so a time can travel one extra hop.

Small example: neighbours at 10:00 (weight 0.9), 10:20 (0.4) and 18:00 (0.4).
Half of the total weight (1.7 / 2 = 0.85) is reached at the first value, so
the estimate is 10:00. The odd 18:00 does not move it.

We measure the error by hiding the clock-precise anchors of some decode
chains, estimating them, and comparing (``evaluate``).

We also test a tempting shortcut and report that it FAILS: reading time from
the order of redaction numbers (``evaluate_token_order``). The numbers were
handed out in discovery order, not time order.

Related ideas: seriation (ordering items by similarity; Atkins, Boman &
Hendrickson, 1998) and happens-before ordering (Lamport, 1978). We use the
simplest form that we can test: neighbours vote on a time.
"""

from __future__ import annotations

import bisect
import random
import statistics
from typing import Dict, List, Tuple

from ..events import EventLog
from .links import Links


def _wmedian(pairs: List[Tuple[float, float]]) -> float:
    pairs = sorted(pairs)
    half = sum(w for _, w in pairs) / 2.0
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= half:
            return v
    return pairs[-1][0]


def propagate(links: Links, known: Dict[int, float], hops: int = 2,
              min_weight: float = 0.4) -> Dict[int, float]:
    """Return {index: time} for events that get a time from neighbours."""
    est = dict(known)
    new: Dict[int, float] = {}
    for _ in range(hops):
        added = {}
        for i in range(len(links.nbr)):
            if i in est:
                continue
            cand = [(est[j], w) for j, w in links.nbr[i] if j in est]
            if cand and sum(w for _, w in cand) >= min_weight:
                added[i] = _wmedian(cand)
        if not added:
            break
        est.update(added)
        new.update(added)
    return new


def _anchors(log: EventLog) -> Dict[int, float]:
    return {i: e.ts for i, e in enumerate(log.events)
            if e.ts is not None and e.ts_source in ("embedded", "chain", "native")}


def _pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 2) if xs else None


def evaluate(log: EventLog, links: Links, folds: int = 5, seed: int = 0, **kw) -> dict:
    """Grouped k-fold test on clock-precise anchors (errors in hours)."""
    anchors = _anchors(log)
    precise = [i for i in anchors if log.events[i].ts_precision == "second"]
    roots = sorted({links.root[i] for i in precise})
    rng = random.Random(seed)
    rng.shuffle(roots)
    errs, base = [], []
    held = 0
    for f in range(folds):
        hold = set(roots[f::folds])
        train = {i: t for i, t in anchors.items() if links.root[i] not in hold}
        if not train:
            continue
        med = statistics.median(train.values())
        guess = propagate(links, train, **kw)
        for i in precise:
            if links.root[i] in hold:
                held += 1
                base.append(abs(med - anchors[i]) / 3600)
                if i in guess:
                    errs.append(abs(guess[i] - anchors[i]) / 3600)
    return dict(
        held_out=held, estimated=len(errs),
        coverage=round(len(errs) / held, 3) if held else None,
        error_hours_median=_pct(errs, 0.5), error_hours_p80=_pct(errs, 0.8),
        error_hours_p90=_pct(errs, 0.9),
        within_1h=round(sum(1 for x in errs if x <= 1) / len(errs), 3) if errs else None,
        within_24h=round(sum(1 for x in errs if x <= 24) / len(errs), 3) if errs else None,
        baseline_median_day_error_hours=_pct(base, 0.5),
    )


def _pava(xs: List[float], ys: List[float]):
    """Monotone (non-decreasing) fit of y on x: pool-adjacent-violators."""
    blocks = []                                       # [sum_y, n, x_start]
    for x, y in sorted(zip(xs, ys)):
        blocks.append([y, 1, x])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n, _ = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
    return [(b[2], b[0] / b[1]) for b in blocks]


def evaluate_token_order(log: EventLog, links: Links, families=("destination", "shortener", "credential"),
                         folds: int = 5, seed: int = 0) -> dict:
    """Does the redaction-number order tell time? (Spoiler: no.)

    For each family, fit a monotone map from the smallest number in an event
    to its time, on training anchors, and measure the error on held-out ones.
    Compare with always guessing the median time.
    """
    anchors = {i: t for i, t in _anchors(log).items() if log.events[i].ts_precision == "second"}
    out = {}
    for fam in families:
        pts = []
        for i, t in anchors.items():
            ids = [int(x) for x in log.events[i].ref_list(fam) if x.isdigit()]
            if ids:
                pts.append((min(ids), t, links.root[i]))
        if len(pts) < 50:
            out[fam] = dict(n=len(pts), note="too few anchors")
            continue
        roots = sorted({p[2] for p in pts})
        rng = random.Random(seed)
        rng.shuffle(roots)
        errs, base = [], []
        for f in range(folds):
            hold = set(roots[f::folds])
            tr = [p for p in pts if p[2] not in hold]
            te = [p for p in pts if p[2] in hold]
            if not tr or not te:
                continue
            model = _pava([p[0] for p in tr], [p[1] for p in tr])
            starts = [m[0] for m in model]
            med = statistics.median(p[1] for p in tr)
            for x, y, _ in te:
                k = max(0, bisect.bisect_right(starts, x) - 1)
                errs.append(abs(model[k][1] - y) / 3600)
                base.append(abs(med - y) / 3600)
        out[fam] = dict(n=len(pts), error_hours_median=_pct(errs, 0.5),
                        baseline_error_hours_median=_pct(base, 0.5),
                        better_than_baseline=(_pct(errs, 0.5) or 1e9) < (_pct(base, 0.5) or 0))
    return out


def run(log: EventLog, links: Links, **kw) -> dict:
    """Infer times for the whole log and write them onto the events."""
    anchors = _anchors(log)
    guess = propagate(links, anchors, **kw)
    for i, t in guess.items():
        e = log.events[i]
        e.ts = t
        e.ts_source = "inferred"
        e.ts_precision = "inferred"
    n = len(log.events)
    return dict(events=n, dated_observed=len(anchors), dated_inferred=len(guess),
                dated_observed_frac=round(len(anchors) / n, 4),
                dated_total_frac=round((len(anchors) + len(guess)) / n, 4))
