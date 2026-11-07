"""Build the temporal interaction graph from an EventLog.

Two graphs come out of the same events:

1. **Bipartite activity graph** -- agents and the resources they touch
   (dead-drops, mailboxes, credentials). Every edge carries a time position so
   the visualization can play it forward. This is the "who touched what, when"
   view and it works even when most events have no known actor.

2. **Agent projection** -- an agent-to-agent graph where two agents are linked
   if they used the same shared resource. This is the "who coordinated with
   whom" view. It is sparse on Swarm Traces (only agents that signed their work
   appear) and dense on attributed logs like AI Village.

The module only uses the Python standard library, so it runs anywhere.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from .events import Event, EventLog


class TemporalGraph:
    """A graph whose edges know when they happened."""

    def __init__(self, axis: str = "sequence"):
        self.axis = axis                       # "time" or "sequence"
        self.nodes: Dict[str, dict] = {}
        self.edges: List[dict] = []

    def add_node(self, nid: str, ntype: str, label: str, pos: int, ts: Optional[float]):
        n = self.nodes.get(nid)
        if n is None:
            self.nodes[nid] = dict(id=nid, type=ntype, label=label,
                                   first_pos=pos, last_pos=pos,
                                   first_ts=ts, last_ts=ts, count=1,
                                   features=Counter())
        else:
            n["last_pos"] = max(n["last_pos"], pos)
            n["count"] += 1
            if ts is not None:
                n["first_ts"] = ts if n["first_ts"] is None else min(n["first_ts"], ts)
                n["last_ts"] = ts if n["last_ts"] is None else max(n["last_ts"], ts)

    def add_edge(self, src: str, dst: str, kind: str, pos: int, ts: Optional[float], eid: str):
        self.edges.append(dict(src=src, dst=dst, kind=kind, pos=pos, ts=ts, eid=eid))


# Resource kinds we draw as nodes in the activity graph (others stay as flags).
_CHANNEL_REF_TYPES = ("destination", "credential", "repo", "webhook")


def build_activity_graph(log: EventLog, prefer_time: bool = True,
                         top_resources: int = 120) -> TemporalGraph:
    """Agents + the resources they touch, as a timed bipartite graph.

    ``top_resources`` keeps the busiest resources so the picture stays readable;
    rare one-off resources are dropped from the drawing (they are still counted
    in detectors).
    """
    ordered = log.sorted_events(prefer_time)
    axis = log.time_axis(prefer_time)
    pos_of = {e.event_id: i for i, e in enumerate(ordered)}

    # Rank resources by how many distinct events touch them.
    res_hits: Counter = Counter()
    for e in log.events:
        if e.channel:
            res_hits[e.channel] += 1
        for rt in _CHANNEL_REF_TYPES:
            for rid in e.ref_list(rt):
                res_hits[f"{rt}:{rid}"] += 1
    keep = {r for r, _ in res_hits.most_common(top_resources)}

    g = TemporalGraph(axis=axis)
    for e in log.events:
        pos = pos_of[e.event_id]
        # agent node
        if e.actor:
            aid = f"agent:{e.actor}"
            g.add_node(aid, "agent", e.actor, pos, e.ts)
            for flag, on in e.features.items():
                if on:
                    g.nodes[aid]["features"][flag] += 1
        # channel node + edge
        targets = []
        if e.channel and e.channel in keep:
            targets.append(e.channel)
        for rt in _CHANNEL_REF_TYPES:
            for rid in e.ref_list(rt):
                rr = f"{rt}:{rid}"
                if rr in keep:
                    targets.append(rr)
        for rr in targets:
            rtype = rr.split(":", 1)[0]
            g.add_node(rr, rtype if rtype in ("mailbox", "dest", "destination",
                                              "credential", "repo", "webhook") else "resource",
                       rr, pos, e.ts)
            if e.actor:
                g.add_edge(f"agent:{e.actor}", rr, "use", pos, e.ts, e.event_id)
        # recipients (channel -> recipient agent)
        for rcp in e.recipients:
            rid = f"agent:{rcp}"
            g.add_node(rid, "agent", rcp, pos, e.ts)
            if e.channel and e.channel in keep:
                g.add_edge(e.channel, rid, "deliver", pos, e.ts, e.event_id)
    return g


def build_agent_projection(log: EventLog, prefer_time: bool = True,
                           min_weight: int = 1) -> Tuple[TemporalGraph, Dict[str, int]]:
    """Agent-to-agent graph via shared resources, with a community label per agent.

    Two agents are linked when they both touch the same channel or dead-drop.
    The edge weight is the number of shared resources. We also run label
    propagation to colour agents into communities.
    """
    ordered = log.sorted_events(prefer_time)
    axis = log.time_axis(prefer_time)
    pos_of = {e.event_id: i for i, e in enumerate(ordered)}

    # resource -> list of (agent, pos, ts)
    touches: Dict[str, List[Tuple[str, int, Optional[float]]]] = defaultdict(list)
    agent_first: Dict[str, Tuple[int, Optional[float]]] = {}
    for e in log.events:
        if not e.actor:
            continue
        pos = pos_of[e.event_id]
        agent_first.setdefault(e.actor, (pos, e.ts))
        res = []
        if e.channel:
            res.append(e.channel)
        for rt in _CHANNEL_REF_TYPES:
            res += [f"{rt}:{rid}" for rid in e.ref_list(rt)]
        for r in res:
            touches[r].append((e.actor, pos, e.ts))

    # Directed edge A->B when A touched a resource before B (write-then-read).
    #
    # Two weights per pair:
    #   * ``count`` -- how many shared resources (raw)
    #   * ``aa``    -- Adamic-Adar: each shared resource adds 1/log(1+k), where k
    #     is how many agents touched it. A resource *everyone* uses (the task's
    #     own API) adds almost nothing; a resource only two agents share adds a
    #     lot. This is the standard fix for "hubs" in link analysis, and it keeps
    #     common task infrastructure from looking like a conspiracy.
    import math
    pair_w: Counter = Counter()
    pair_aa: Dict[Tuple[str, str], float] = defaultdict(float)
    pair_pos: Dict[Tuple[str, str], Tuple[int, Optional[float]]] = {}
    pair_lead: Dict[Tuple[str, str], str] = {}
    for r, lst in touches.items():
        lst_sorted = sorted(lst, key=lambda x: x[1])
        k = len({a for a, _, _ in lst_sorted})
        aa = 1.0 / math.log(1 + k) if k > 1 else 0.0
        first_seen: Dict[str, Tuple[int, Optional[float]]] = {}
        for agent, pos, ts in lst_sorted:
            if agent not in first_seen:
                first_seen[agent] = (pos, ts)
        order = sorted(first_seen.items(), key=lambda x: x[1][0])
        for i, (a, (pa, ta)) in enumerate(order):
            for b, (pb, tb) in order[i + 1:]:
                # One undirected score per pair, so evidence is never split
                # between A->B and B->A. We remember who moved first on the
                # earliest shared resource as the edge direction.
                key = (a, b) if a < b else (b, a)
                pair_w[key] += 1
                pair_aa[key] += aa
                if key not in pair_pos or pb < pair_pos[key][0]:
                    pair_pos[key] = (pb, tb)
                    pair_lead[key] = a

    g = TemporalGraph(axis=axis)
    for a, (pos, ts) in agent_first.items():
        g.add_node(f"agent:{a}", "agent", a, pos, ts)
    for (a, b), w in pair_w.items():
        if w >= min_weight:
            pos, ts = pair_pos[(a, b)]
            lead = pair_lead.get((a, b), a)
            other = b if lead == a else a
            g.add_edge(f"agent:{lead}", f"agent:{other}", "coordinate", pos, ts, f"{lead}->{other}")
            g.edges[-1]["count"] = w
            g.edges[-1]["weight"] = round(pair_aa[(a, b)], 4)

    comms = _label_propagation(g)
    for nid, c in comms.items():
        if nid in g.nodes:
            g.nodes[nid]["community"] = c
    return g, comms


def _label_propagation(g: TemporalGraph, rounds: int = 20) -> Dict[str, int]:
    """Tiny community detection with no third-party dependency.

    Each node starts in its own community, then repeatedly adopts the most
    common community among its neighbours. Deterministic tie-breaking keeps
    results stable across runs.
    """
    adj: Dict[str, Counter] = defaultdict(Counter)
    for e in g.edges:
        w = e.get("weight", 1)
        adj[e["src"]][e["dst"]] += w
        adj[e["dst"]][e["src"]] += w
    labels = {n: i for i, n in enumerate(sorted(g.nodes))}
    for _ in range(rounds):
        changed = False
        for n in sorted(g.nodes):
            if not adj[n]:
                continue
            tally: Counter = Counter()
            for nb, w in adj[n].items():
                tally[labels[nb]] += w
            best = min((-c, lab) for lab, c in tally.items())[1]
            if labels[n] != best:
                labels[n] = best
                changed = True
        if not changed:
            break
    # renumber communities 0..k-1 by size
    order = [lab for lab, _ in Counter(labels.values()).most_common()]
    remap = {lab: i for i, lab in enumerate(order)}
    return {n: remap[l] for n, l in labels.items()}
