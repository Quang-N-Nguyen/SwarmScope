"""Information-spread detector.

Picks a "piece of information" -- a specific credential, dead-drop destination,
or repository id -- and reconstructs how it moved through the swarm over time:
who touched it first, who touched it next, and how many agents/events it reached.

This is the direct answer to "how did a piece of information spread through the
swarm?" On Swarm Traces the natural information items are the harvested
credentials (the agents called their collection "LOOT") and the dataset ids used
as dead-drops.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from ..events import EventLog
from ..graph import _CHANNEL_REF_TYPES


def _item_events(log: EventLog, ref_type: str, item_id: str, prefer_time: bool) -> List[dict]:
    ordered = log.sorted_events(prefer_time)
    touches = []
    for pos, e in enumerate(ordered):
        if item_id in e.ref_list(ref_type) or e.channel == f"{ref_type}:{item_id}":
            touches.append(dict(pos=pos, ts=e.ts, actor=e.actor,
                                event_id=e.event_id, kind=e.kind))
    return touches


def trace_item(log: EventLog, ref_type: str, item_id: str,
               prefer_time: bool = True) -> dict:
    """Reconstruct the spread of one information item.

    Returns the ordered touch list, the reach curve (distinct actors seen so
    far at each step), and a simple spread velocity (events per axis step
    between first and last touch).
    """
    touches = _item_events(log, ref_type, item_id, prefer_time)
    seen = set()
    reach_curve = []
    for i, t in enumerate(touches):
        if t["actor"]:
            seen.add(t["actor"])
        reach_curve.append(dict(step=i, pos=t["pos"], distinct_actors=len(seen)))
    first = touches[0] if touches else None
    last = touches[-1] if touches else None
    span = (last["pos"] - first["pos"]) if (first and last) else 0
    return dict(
        item=f"{ref_type}:{item_id}",
        n_touches=len(touches),
        n_distinct_actors=len(seen),
        first_touch=first,
        last_touch=last,
        axis_span=span,
        velocity=round(len(touches) / span, 4) if span else None,
        touches=touches[:500],
        reach_curve=reach_curve[:500],
    )


def rank_items(log: EventLog, ref_type: str = "credential", top: int = 20) -> List[dict]:
    """Find the information items that spread widest, to trace automatically.

    Ranks items by how many distinct events (and named agents) touched them.
    """
    ev_count: Counter = Counter()
    actor_sets: Dict[str, set] = {}
    for e in log.events:
        ids = list(e.ref_list(ref_type))
        if e.channel and e.channel.startswith(f"{ref_type}:"):
            ids.append(e.channel.split(":", 1)[1])
        for i in set(ids):
            ev_count[i] += 1
            actor_sets.setdefault(i, set())
            if e.actor:
                actor_sets[i].add(e.actor)
    rows = [dict(item_id=i, n_events=c, n_agents=len(actor_sets.get(i, ())))
            for i, c in ev_count.items()]
    rows.sort(key=lambda x: (-x["n_agents"], -x["n_events"]))
    return rows[:top]


def run_all(log: EventLog, prefer_time: bool = True) -> dict:
    out = {}
    for ref_type in ("credential", "destination"):
        ranked = rank_items(log, ref_type, top=10)
        traces = []
        for row in ranked[:5]:
            traces.append(trace_item(log, ref_type, row["item_id"], prefer_time))
        out[ref_type] = dict(ranked=ranked, traces=traces)
    return out
