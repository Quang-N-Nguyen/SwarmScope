"""Is the group more than the sum of its agents? (Riedl's emergence test)

Riedl (2025/2026, "Emergent Coordination in Multi-Agent Language Models",
arXiv:2510.05174) asks whether a group's future is predicted better by the
group as a whole than by its members one at a time. We apply his two
criteria to agent activity over time:

* X_i,t  = agent i's number of chat messages in time bin t, split into 2
  levels at its own median (quantile binning, K = 2, as in the paper);
* V_t    = the group total (sum of the agents' counts), also split in 2.

1. **Practical criterion**
       S = I(V_t ; V_t+1)  -  sum_i I(X_i,t ; V_t+1)
   S > 0 means the group total predicts its own future better than all the
   individual agents added up: "dynamical synergy".
2. **Emergence capacity** -- for each pair (i, j), a two-source partial
   information decomposition (Williams & Beer, I_min redundancy) of
       I({X_i,t, X_j,t} ; (X_i,t+1, X_j,t+1)) = Unique_i + Unique_j + Redundant + Synergy
   and the median Synergy over all pairs.

Probabilities use a Jeffreys prior (add 1/2 to every cell), as in the paper.
**Null**: 200 surrogates where each agent's series is circularly shifted by
its own random offset. This keeps every agent's own rhythm but breaks the
timing between agents. Bias-corrected value = observed - median(null);
p = (1 + #null >= observed) / (B + 1).

Riedl uses groups of 10 agents. We do the same: the 10 most active agents,
plus random groups of 10, so villages of different sizes are comparable.

Small example: if 10 agents always post in the same hours (a shared
schedule), shifting each agent's series breaks that, the null gives low
synergy, and the observed value stands out (p small). If agents post
independently, the observed value looks like the null (p near 0.5).
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from itertools import combinations
from typing import Dict, List, Optional, Sequence, Tuple

from ..events import EventLog

ALPHA = 0.5   # Jeffreys prior


def _entropy(counts: Dict, k: int) -> float:
    """Entropy (bits) of a distribution over k cells with Jeffreys smoothing."""
    n = sum(counts.values()) + ALPHA * k
    h = 0.0
    for c in list(counts.values()) + [0] * (k - len(counts)):
        p = (c + ALPHA) / n
        h -= p * math.log2(p)
    return h


def mi(x: Sequence, y: Sequence, kx: int = 2, ky: int = 2) -> float:
    """I(X;Y) in bits from paired samples."""
    hx = _entropy(Counter(x), kx)
    hy = _entropy(Counter(y), ky)
    hxy = _entropy(Counter(zip(x, y)), kx * ky)
    return max(0.0, hx + hy - hxy)


def pid_synergy(a: Sequence, b: Sequence, t: Sequence, ka: int = 2, kb: int = 2, kt: int = 4) -> float:
    """Williams-Beer synergy with I_min redundancy for sources a, b and target t."""
    return pid_parts(a, b, t, ka, kb, kt)[0]


def pid_parts(a: Sequence, b: Sequence, t: Sequence, ka: int = 2, kb: int = 2, kt: int = 4) -> Tuple[float, float]:
    """(synergy, redundancy) of the Williams-Beer decomposition (I_min redundancy)."""
    n = len(t)
    joint = Counter(zip(a, b, t))
    cells = ka * kb * kt
    tot = n + ALPHA * cells
    p = {}
    for i in range(ka):
        for j in range(kb):
            for k in range(kt):
                p[(i, j, k)] = (joint.get((i, j, k), 0) + ALPHA) / tot
    pt = defaultdict(float); pa = defaultdict(float); pb = defaultdict(float)
    pat = defaultdict(float); pbt = defaultdict(float); pab = defaultdict(float)
    for (i, j, k), v in p.items():
        pt[k] += v; pa[i] += v; pb[j] += v
        pat[(i, k)] += v; pbt[(j, k)] += v; pab[(i, j)] += v

    def mi_from(pxy, px):
        return sum(v * math.log2(v / (px[x] * pt[y])) for (x, y), v in pxy.items() if v > 0)

    i_a = mi_from(pat, pa)
    i_b = mi_from(pbt, pb)
    i_ab = sum(v * math.log2(v / (pab[(i, j)] * pt[k])) for (i, j, k), v in p.items() if v > 0)
    red = 0.0
    for k in range(kt):
        # specific information of each source about T = k
        sa = sum((pat[(i, k)] / pt[k]) * math.log2((pat[(i, k)] / pa[i]) / pt[k]) for i in range(ka))
        sb = sum((pbt[(j, k)] / pt[k]) * math.log2((pbt[(j, k)] / pb[j]) / pt[k]) for j in range(kb))
        red += pt[k] * min(sa, sb)
    return i_ab - i_a - i_b + red, red


def _binarize(xs: List[float], use: Optional[Sequence[int]] = None) -> List[int]:
    """1 if above the median, else 0. The median is taken over the positions
    the test uses (``use``): with empty night/weekend bins included, the median
    of a scheduled log is 0 and every used bin would count as "high"."""
    s = sorted(xs[i] for i in use) if use is not None else sorted(xs)
    med = s[len(s) // 2]
    # "above the median" (if the median is 0, that is simply "active")
    return [1 if x > med else 0 for x in xs]


def _measures(series: List[List[float]], pairs_idx: List[Tuple[int, int]]) -> Tuple[float, float, float]:
    """(practical S, median pairwise synergy, median pairwise redundancy)."""
    tot = [sum(col) for col in zip(*series)]
    used = sorted({i for p in pairs_idx for i in p})
    X = [_binarize(s, used) for s in series]
    V = _binarize(tot, used)
    idx = pairs_idx
    v_now = [V[t] for t, _ in idx]
    v_next = [V[u] for _, u in idx]
    s = mi(v_now, v_next) - sum(mi([x[t] for t, _ in idx], v_next) for x in X)
    syn, red = [], []
    for a, b in combinations(range(len(X)), 2):
        xa = [X[a][t] for t, _ in idx]
        xb = [X[b][t] for t, _ in idx]
        target = [2 * X[a][u] + X[b][u] for _, u in idx]
        sy, rd = pid_parts(xa, xb, target)
        syn.append(sy); red.append(rd)
    syn.sort(); red.sort()
    return s, (syn[len(syn) // 2] if syn else 0.0), (red[len(red) // 2] if red else 0.0)


def _shift(s: List[float], k: int) -> List[float]:
    return s[k:] + s[:k] if s else s


def group_test(series: List[List[float]], pairs_idx, B: int = 200, seed: int = 0, step: int = 1) -> dict:
    """``step`` = shift unit in bins. For logs on a daily schedule we shift by
    whole days only, so a shared working-hours rhythm stays in the null and
    cannot pass for coordination."""
    rnd = random.Random(seed)
    obs_s, obs_syn, obs_red = _measures(series, pairs_idx)
    T = len(series[0])
    null_s, null_syn, null_red = [], [], []
    n_steps = max(2, T // step)
    for _ in range(B):
        sh = [_shift(s, step * rnd.randrange(1, n_steps)) for s in series]
        a, b, c = _measures(sh, pairs_idx)
        null_s.append(a); null_syn.append(b); null_red.append(c)
    med = lambda v: sorted(v)[len(v) // 2]
    return dict(practical=round(obs_s, 4), practical_corrected=round(obs_s - med(null_s), 4),
                practical_p=round((1 + sum(1 for v in null_s if v >= obs_s)) / (B + 1), 4),
                synergy=round(obs_syn, 4), synergy_corrected=round(obs_syn - med(null_syn), 4),
                synergy_p=round((1 + sum(1 for v in null_syn if v >= obs_syn)) / (B + 1), 4),
                redundancy=round(obs_red, 4), redundancy_corrected=round(obs_red - med(null_red), 4),
                redundancy_p=round((1 + sum(1 for v in null_red if v >= obs_red)) / (B + 1), 4))


def activity_series(log: EventLog, bin_minutes: Optional[int] = None, min_active_bins: int = 100):
    """Per-agent message counts per bin, over ACTIVE bins only (bins with at
    least one agent message), in time order. ``pairs_idx`` holds positions
    (p, p+1) of two active bins that are also next to each other in time.

    Logs on a daily schedule (longer than 3 days) are de-trended: each count
    minus that agent's mean count for the same hour of day. Otherwise agents
    that keep the same working hours look "coordinated". This follows the
    paper's time-trend control (residualisation).
    """
    msgs = [(e.ts, e.actor) for e in log.timed_events()
            if e.kind == "chat" and e.actor and not str(e.actor).startswith("human:")]
    if len(msgs) < 200:
        return None
    t0, t1 = msgs[0][0], msgs[-1][0]
    if bin_minutes is None:
        span_h = (t1 - t0) / 3600
        bin_minutes = 10 if span_h <= 48 else (30 if span_h <= 24 * 7 else 60)
    W = bin_minutes * 60
    counts: Dict[int, Counter] = defaultdict(Counter)
    for t, a in msgs:
        counts[int((t - t0) // W)][a] += 1
    bins = sorted(counts)                       # active bins only
    pairs_idx = [(i, i + 1) for i in range(len(bins) - 1) if bins[i + 1] == bins[i] + 1]
    if len(pairs_idx) < min_active_bins:
        return None
    daily = (t1 - t0) > 3 * 86400
    hour = [int(((t0 + b * W) % 86400) // 3600) for b in bins]
    total = Counter()
    for c in counts.values():
        total.update(c)
    return dict(bin_minutes=bin_minutes, bins=bins, counts=counts, pairs_idx=pairs_idx, total=total,
                daily=daily, hour=hour)


def _series(a: dict, agent: str, lo: int, hi: int) -> List[float]:
    xs = [a["counts"][a["bins"][i]].get(agent, 0) for i in range(lo, hi + 1)]
    if a["daily"]:
        hrs = a["hour"][lo:hi + 1]
        mean = defaultdict(list)
        for h, x in zip(hrs, xs):
            mean[h].append(x)
        m = {h: sum(v) / len(v) for h, v in mean.items()}
        xs = [x - m[h] for h, x in zip(hrs, xs)]
    return xs


def run_all(log: EventLog, group_size: int = 10, n_random: int = 10, B: int = 200, seed: int = 7,
            min_transitions: int = 50) -> dict:
    """Test the most active group of agents and ``n_random`` random groups.

    Each group is cut to the period when ALL its members were active (first
    to last message of each). In a log where agents join and leave over months
    (main-village: 18 months, models retire), shifting an agent's series would
    otherwise move it into months when the others were absent. Random groups
    are drawn among agents whose active periods overlap.
    """
    a = activity_series(log)
    if not a:
        return {}
    agents = [x for x, _ in a["total"].most_common()]
    if len(agents) < 3:
        return {}
    k = min(group_size, len(agents))
    span: Dict[str, List[int]] = {}
    for i, b in enumerate(a["bins"]):
        for g in a["counts"][b]:
            span.setdefault(g, [i, i])[1] = i

    def test(group, sd):
        lo = max(span[g][0] for g in group)
        hi = min(span[g][1] for g in group)
        pairs = [(p - lo, q - lo) for p, q in a["pairs_idx"] if lo <= p and q <= hi]
        if len(pairs) < min_transitions:
            return None
        ser = [_series(a, g, lo, hi) for g in group]
        r = group_test(ser, pairs, B, sd)
        r.update(transitions=len(pairs))
        return r

    def overlaps(g, ref):
        lo, hi = span[ref]
        return min(hi, span[g][1]) - max(lo, span[g][0]) >= 0.5 * (hi - lo)

    pool = [x for x in agents if a["total"][x] >= 20] or agents
    top = [pool[0]] + [g for g in pool[1:] if overlaps(g, pool[0])][:k - 1]
    out = dict(bin_minutes=a["bin_minutes"], transitions=len(a["pairs_idx"]), group_size=k, permutations=B,
               detrended_by_hour=a["daily"],
               null="circular shifts along active bins" + (", after removing each agent's hour-of-day mean"
                                                            if a["daily"] else ""),
               top_group=dict(agents=top, **(test(top, seed) or {"skipped": "too few common active bins"})))
    rnd = random.Random(seed)
    rand, tries = [], 0
    while len(pool) > k and len(rand) < n_random and tries < n_random * 30:
        tries += 1
        anchor = rnd.choice(pool)
        near = [g for g in pool if g != anchor and overlaps(g, anchor)]
        if len(near) < k - 1:
            continue
        r = test([anchor] + rnd.sample(near, k - 1), seed + tries)
        if r:
            rand.append(r)
    out["random_groups"] = rand
    if rand:
        for m in ("synergy", "practical", "redundancy"):
            out[f"random_groups_{m}_significant"] = sum(1 for r in rand if r[f"{m}_p"] < 0.05)
    return out
