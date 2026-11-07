"""Who talked to whom, for attributed chat logs (AI Village, generic logs).

When a log says who spoke and whom they addressed (``@name``), we do not need
to infer interaction through dead-drops: the addressing itself is the edge.
This module measures the shape of that network, split into the phases the
log's milestones define (for AI Village, the operator messages).

Measures (all on directed "A addressed B" edges):

* **reciprocity** -- share of addressed pairs where B also addressed A.
* **attention Gini** -- how unequal incoming attention is (0 = everyone is
  addressed equally, 1 = one agent gets all of it). A rising Gini means the
  group is centralising around a few agents: emergent leadership, which
  Hammond et al. (2025) list under emergent agency / network effects.
* **hubs** -- most-addressed agents. **brokers** -- agents on many shortest
  paths between others (betweenness; Brandes, 2001).
* **reply latency** -- after A addresses B, how long until B addresses A.

Small example: 4 agents, A addressed by everyone 9 times, B/C/D once each.
In-degree list [9, 1, 1, 1]: Gini = 0.5. If all four got 3, Gini = 0.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from ..events import EventLog
from .research import _betweenness


def gini(values: List[float]) -> float:
    """Gini coefficient of non-negative values (0 = equal, 1 = concentrated)."""
    xs = sorted(v for v in values if v >= 0)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return round((2 * cum) / (n * sum(xs)) - (n + 1) / n, 3)


def phases(log: EventLog) -> List[Tuple[str, float, float]]:
    """Time windows between consecutive milestones: [(label, start, end)].

    The first milestone is treated as the start of the log. Without
    milestones, the whole log is one window.
    """
    timed = log.timed_events()
    if not timed:
        return []
    t0, t1 = timed[0].ts, timed[-1].ts + 1
    ms = sorted((getattr(log, "milestones", {}) or {}).items(), key=lambda x: x[1])
    labels = getattr(log, "milestone_labels", {}) or {}
    cuts = [(k, v) for k, v in ms if t0 < v < t1]
    out = []
    start, label = t0, "Start"
    for k, v in cuts:
        out.append((label, start, v))
        start, label = v, labels.get(k, k)
    out.append((label, start, t1))
    return [(lab, a, b) for lab, a, b in out if b - a >= 600]   # skip windows under 10 minutes


def _edges(log: EventLog, t_from: float = float("-inf"), t_to: float = float("inf")) -> Counter:
    e = Counter()
    for ev in log.events:
        if ev.actor and ev.ts is not None and t_from <= ev.ts < t_to:
            for r in ev.recipients:
                if r != ev.actor:
                    e[(ev.actor, r)] += 1
    return e


def network_stats(log: EventLog, t_from: float = float("-inf"), t_to: float = float("inf"),
                  top: int = 8) -> dict:
    edges = _edges(log, t_from, t_to)
    speakers = {ev.actor for ev in log.events
                if ev.actor and ev.kind == "chat" and ev.ts is not None and t_from <= ev.ts < t_to}
    indeg: Counter = Counter()
    outdeg: Counter = Counter()
    for (a, b), w in edges.items():
        indeg[b] += w
        outdeg[a] += w
    pairs = set(edges)
    recip = sum(1 for (a, b) in pairs if (b, a) in pairs) / len(pairs) if pairs else 0.0
    nodes = sorted(speakers | {b for _, b in pairs})
    adj: Dict[str, set] = defaultdict(set)
    for a, b in pairs:
        adj[a].add(b)
        adj[b].add(a)
    bc = _betweenness(nodes, adj) if 2 < len(nodes) <= 400 else {}
    hours = (t_to - t_from) / 3600 if t_to != float("inf") and t_from != float("-inf") else None
    return dict(
        speakers=len(speakers), addressed_pairs=len(pairs), addresses=sum(edges.values()),
        addresses_per_hour=round(sum(edges.values()) / hours, 1) if hours else None,
        reciprocity=round(recip, 3),
        # Gini over AI agents only: many viewers speak once and are never
        # addressed, which would push the Gini towards 1 for the wrong reason.
        attention_gini=gini([indeg.get(n, 0) for n in nodes if not str(n).startswith("human:")]),
        top_hub_share=round(indeg.most_common(1)[0][1] / sum(indeg.values()), 3) if indeg else 0.0,
        hubs=indeg.most_common(top),
        most_addressing=outdeg.most_common(top),
        brokers=[(a, round(v, 4)) for a, v in sorted(bc.items(), key=lambda x: -x[1])[:top] if v > 0],
    )


def reply_latency(log: EventLog, max_wait_hours: float = 6.0) -> dict:
    """After A addresses B, minutes until B next addresses A (within max wait)."""
    by_pair: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for ev in log.timed_events():
        if ev.actor:
            for r in ev.recipients:
                by_pair[(ev.actor, r)].append(ev.ts)
    lat = []
    asked = answered = 0
    for (a, b), times in by_pair.items():
        back = sorted(by_pair.get((b, a), []))
        for t in times:
            asked += 1
            nxt = next((x for x in back if x > t), None)
            if nxt is not None and nxt - t <= max_wait_hours * 3600:
                answered += 1
                lat.append((nxt - t) / 60)
    lat.sort()
    return dict(addresses=asked, answered=answered,
                answered_frac=round(answered / asked, 3) if asked else None,
                median_minutes=round(lat[len(lat) // 2], 1) if lat else None)


def run_all(log: EventLog) -> dict:
    if not any(e.recipients for e in log.events):
        return {}
    out = dict(overall=network_stats(log), latency=reply_latency(log), phases=[])
    for label, a, b in phases(log):
        st = network_stats(log, a, b, top=5)
        st.update(label=label, start=a, end=b)
        out["phases"].append(st)
    return out
