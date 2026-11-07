"""Coordination detectors.

These answer "who is working together, and does it look organised?" They do not
judge intent -- they surface structure an investigator would want to look at.

Signals produced:

* **shared dead-drops** -- resources touched by two or more agents (the clearest
  sign of coordination in a de-identified log)
* **synchronised bursts** -- short windows with a spike of activity
* **repeated dyads** -- agent pairs that interact again and again
* **duplicate-control** -- agents claiming locks / killing rivals, i.e. one swarm
  managing itself
* **communities** -- clusters from the agent projection graph
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional

from ..events import EventLog
from ..graph import build_agent_projection, _CHANNEL_REF_TYPES


def shared_deaddrops(log: EventLog, min_agents: int = 2, top: int = 50) -> List[dict]:
    """Resources that two or more named agents both touched.

    Each row is flagged with ``task_api`` (share of events that are ordinary
    calls to the assigned task's own submission API -- shared because every agent
    was given it, not because of coordination) and ``coord_use`` (share of events
    that are board / mailbox writes -- a resource that exists only for agents to
    talk to each other). High ``coord_use`` + low ``task_api`` is the interesting
    kind of dead-drop.
    """
    res_agents: Dict[str, set] = defaultdict(set)
    res_events: Dict[str, int] = Counter()
    res_submit: Dict[str, int] = Counter()
    res_board: Dict[str, int] = Counter()
    for e in log.events:
        targets = []
        if e.channel:
            targets.append(e.channel)
        for rt in _CHANNEL_REF_TYPES:
            targets += [f"{rt}:{rid}" for rid in e.ref_list(rt)]
        for r in set(targets):
            res_events[r] += 1
            if e.has("task_submit"):
                res_submit[r] += 1
            if e.has("board_token") or e.has("mailbox"):
                res_board[r] += 1
            if e.actor:
                res_agents[r].add(e.actor)
    rows = []
    for r, agents in res_agents.items():
        if len(agents) >= min_agents:
            n = res_events[r] or 1
            rows.append(dict(resource=r, n_agents=len(agents),
                             agents=sorted(agents)[:20], n_events=res_events[r],
                             task_api=round(res_submit[r] / n, 2),
                             coord_use=round(res_board[r] / n, 2)))
    rows.sort(key=lambda x: (-x["n_agents"], -x["n_events"]))
    return rows[:top]


def synchronized_bursts(log: EventLog, prefer_time: bool = True,
                        window: int = 200, z: float = 3.0) -> List[dict]:
    """Windows along the axis with an unusually high number of events.

    We slide a fixed-size window over the ordered events and flag windows whose
    event count is ``z`` standard deviations above the mean. A spike of activity
    is where coordinated action tends to show up.
    """
    ordered = log.sorted_events(prefer_time)
    n = len(ordered)
    if n < window * 2:
        window = max(10, n // 10)
    counts = []
    for start in range(0, n, window):
        chunk = ordered[start:start + window]
        counts.append(len(chunk))
    if len(counts) < 3:
        return []
    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / len(counts)
    sd = var ** 0.5 or 1.0
    rows = []
    for i, c in enumerate(counts):
        if (c - mean) / sd >= z:
            chunk = ordered[i * window:(i + 1) * window]
            actors = Counter(e.actor for e in chunk if e.actor)
            feats = Counter()
            for e in chunk:
                for f, on in e.features.items():
                    if on:
                        feats[f] += 1
            rows.append(dict(window_index=i, start_pos=i * window, n_events=c,
                             zscore=round((c - mean) / sd, 2),
                             top_actors=actors.most_common(5),
                             top_mechanisms=feats.most_common(5)))
    return rows


def repeated_dyads(log: EventLog, prefer_time: bool = True, top: int = 40) -> List[dict]:
    """Agent pairs ranked by how *telling* their shared resources are.

    We rank by the Adamic-Adar score, not the raw count, so pairs that share
    rare resources (a two-agent mailbox) rank above pairs that merely both used
    the task's own API. Raw count is kept for context.
    """
    g, _ = build_agent_projection(log, prefer_time)
    rows = []
    for e in g.edges:
        rows.append(dict(src=e["src"].split(":", 1)[1], dst=e["dst"].split(":", 1)[1],
                         shared=e.get("count", 1), score=e.get("weight", 0)))
    rows.sort(key=lambda x: (-x["score"], -x["shared"]))
    return rows[:top]


def duplicate_control(log: EventLog, top: int = 40) -> dict:
    """Agents that managed the swarm itself: locks, elections, killing rivals."""
    actors = Counter()
    events = []
    for e in log.events:
        if e.has("lock_dupctrl") and (e.has("board_token") or e.has("mailbox") or e.actor):
            if e.actor:
                actors[e.actor] += 1
            events.append(e.event_id)
    return dict(n_events=len(events), top_controllers=actors.most_common(top),
                example_event_ids=events[:20])


def communities(log: EventLog, prefer_time: bool = True) -> dict:
    """Cluster the named agents into communities via the projection graph."""
    g, comms = build_agent_projection(log, prefer_time)
    by_comm: Dict[int, List[str]] = defaultdict(list)
    for nid, c in comms.items():
        if nid.startswith("agent:"):
            by_comm[c].append(nid.split(":", 1)[1])
    sizes = sorted(((c, len(v)) for c, v in by_comm.items()), key=lambda x: -x[1])
    return dict(n_communities=len(by_comm),
                n_nontrivial=sum(1 for _, s in sizes if s >= 2),
                n_isolated=sum(1 for _, s in sizes if s == 1),
                sizes=sizes[:20],
                members={str(c): sorted(v)[:30] for c, v in list(by_comm.items())[:10]})


def alias_groups(log: EventLog, top: int = 30) -> List[dict]:
    """Handles that are probably one agent using several names.

    Agents choose their own handles, and often add a suffix letter when they
    restart (URI23816C, URI23816D). We group handles that share the same
    letters-then-digits stem. This is only a hint: two agents can pick the same
    stem by chance.
    """
    import re
    stem_rx = re.compile(r"^([A-Z]+\d+)")
    groups: Dict[str, set] = defaultdict(set)
    counts: Counter = Counter(e.actor for e in log.events if e.actor)
    for h in counts:
        m = stem_rx.match(h)
        if m:
            groups[m.group(1)].add(h)
    rows = [dict(stem=s, handles=sorted(hs), n_events=sum(counts[h] for h in hs))
            for s, hs in groups.items() if len(hs) >= 2]
    rows.sort(key=lambda x: (-len(x["handles"]), -x["n_events"]))
    return rows[:top]


def run_all(log: EventLog, prefer_time: bool = True) -> dict:
    return dict(
        alias_groups=alias_groups(log),
        shared_deaddrops=shared_deaddrops(log),
        synchronized_bursts=synchronized_bursts(log, prefer_time),
        repeated_dyads=repeated_dyads(log, prefer_time),
        duplicate_control=duplicate_control(log),
        communities=communities(log, prefer_time),
    )
