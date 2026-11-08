"""How did a piece of information spread? (attributed logs)

An "item" is anything an agent can pick up from others: a file name
(``OWNERS.md``), a commit hash, or a new word that one agent coins and others
start using. For each item we record each agent's *first* use, in time order.
That gives:

* **origin**   -- the first agent to use it
* **reach**    -- how many agents used it
* **time to half** -- hours until half of those agents had used it
* **transmission tree** -- for each adopter, a *probable source*: among
  agents who used the item earlier, the one who most recently addressed the
  adopter (``@name``) before adoption; if nobody did, the most recent earlier
  user. This is an exposure model, the same idea used to reconstruct
  information cascades in social networks (Goel, Watts & Goldstein, 2012).
* **depth** of the tree and mean **branching** (adopters each user passed it on to).

Small example: A uses "OWNERS.md" at 10:00, B at 10:05, C at 10:30. C was
addressed by A at 10:20, so C's probable source is A (not B, the latest user).
Tree: A -> B, A -> C. Depth 1, branching 2 (A) and 0 (B, C).

``trace`` follows a regular expression instead of an item, for case studies
such as "who talked about their role changing after the operator error".
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ..events import EventLog

# Words too common or too generic to be "information" that spreads.
_STOP = set("""
about above after again against agent agents along already also although always among another
anyone anything around because been before being below between both build built cannot change
changes check could doing done down during each either else enough every everyone everything first
from further going good great have having here into itself just keep know last later least less
like little made make many maybe more most much must need needs next nothing only other others
over please probably really right same should since some something still such sure take than
thanks that their them then there these they thing things think this those though through time
today together under until upon very want well were what when where which while will with within
without work working would yeah your yours role roles world agent phase thank update updated
""".split())

_WORD = re.compile(r"[a-z][a-z_\-]{4,30}")
_TERM = re.compile(r"(?<![\w-])([a-z][a-z0-9]*(?:[_-][a-z0-9]+)+)(?![\w-])")


def _first_uses(log: EventLog, items_of: Callable) -> Dict[str, List[Tuple[float, str, str]]]:
    """item -> [(ts, agent, event_id)] of each agent's first use, in time order."""
    first: Dict[str, Dict[str, Tuple[float, str]]] = defaultdict(dict)
    for ev in log.timed_events():
        if not ev.actor or ev.kind != "chat" or ev.actor.startswith("human:"):
            continue
        for it in set(items_of(ev)):
            if ev.actor not in first[it]:
                first[it][ev.actor] = (ev.ts, ev.event_id)
    return {it: sorted((t, a, eid) for a, (t, eid) in d.items()) for it, d in first.items()}


def _address_times(log: EventLog) -> Dict[Tuple[str, str], List[float]]:
    at: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for ev in log.timed_events():
        if ev.actor:
            for r in ev.recipients:
                at[(ev.actor, r)].append(ev.ts)
    return at


def cascade(uses: List[Tuple[float, str, str]], addr: Dict[Tuple[str, str], List[float]]) -> dict:
    """Build the transmission tree for one item (see module docstring)."""
    if not uses:
        return {}
    origin = uses[0][1]
    parent: Dict[str, Optional[str]] = {origin: None}
    via_address = 0
    for i, (t, a, _) in enumerate(uses[1:], start=1):
        earlier = uses[:i]
        best, best_t = None, -1.0
        for (te, b, _) in earlier:
            for x in addr.get((b, a), ()):
                if x <= t and x > best_t:
                    best, best_t = b, x
        if best is not None:
            via_address += 1
        else:
            best = earlier[-1][1]
        parent[a] = best
    children = Counter(p for p in parent.values() if p)
    def depth(n):
        d = 0
        while parent.get(n):
            n = parent[n]
            d += 1
        return d
    times = [t for t, _, _ in uses]
    half = times[(len(times) - 1) // 2]
    return dict(origin=origin, reach=len(uses),
                first_ts=times[0], last_ts=times[-1],
                hours_to_half=round((half - times[0]) / 3600, 2),
                span_hours=round((times[-1] - times[0]) / 3600, 2),
                depth=max(depth(n) for n in parent),
                mean_branching=round(sum(children.values()) / len(parent), 2),
                top_spreaders=children.most_common(3),
                sourced_by_address=round(via_address / (len(uses) - 1), 3) if len(uses) > 1 else None,
                tree=[(parent[a], a) for _, a, _ in uses[1:]][:200],
                times=[round(t) for t in times])   # first-use time of each adopter, for charts


def spreading_items(log: EventLog, kind: str = "file", min_reach: int = 8, top: int = 10) -> List[dict]:
    """Files, commits, or coined words that spread to at least ``min_reach`` agents.

    For words ("term"), we keep only words that appeared after the first hour
    of the log and were used by a single agent during their first 15 minutes,
    i.e. coined by someone and then picked up by others.
    """
    if kind == "term":
        # Identifier-like terms only (snake_case or kebab-case, e.g.
        # "starting_assets", "join-path"). Plain words like "filed" spread
        # trivially because everyone speaks English; coined identifiers do not.
        names = {e.actor.lower() for e in log.events if e.actor}
        items_of = lambda ev: [w for w in _TERM.findall((ev.meta.get("text_lc") or ""))
                               if w not in _STOP and w not in names]
    else:
        items_of = lambda ev: ev.ref_list(kind)
    uses = _first_uses(log, items_of)
    addr = _address_times(log)
    timed = log.timed_events()
    t_start = timed[0].ts if timed else 0
    rows = []
    for it, u in uses.items():
        if len(u) < min_reach:
            continue
        if kind == "term":
            if u[0][0] < t_start + 3600:
                continue
            if sum(1 for t, _, _ in u if t <= u[0][0] + 900) > 1:
                continue
        c = cascade(u, addr)
        c["item"] = it
        rows.append(c)
    rows.sort(key=lambda r: (-r["reach"], r["hours_to_half"], str(r["item"])))   # item name breaks ties: same order every run
    return rows[:top]


def trace(log: EventLog, pattern: str, since: Optional[float] = None, until: Optional[float] = None,
          bucket_minutes: int = 30) -> dict:
    """Follow a regular expression through the chat: who said it, when, how fast it spread."""
    rx = re.compile(pattern, re.I)
    def items_of(ev):
        if since is not None and ev.ts < since:
            return []
        if until is not None and ev.ts >= until:
            return []
        return ["match"] if rx.search(ev.meta.get("text_lc") or "") else []
    uses = _first_uses(log, items_of).get("match", [])
    if not uses:
        return dict(pattern=pattern, reach=0)
    c = cascade(uses, _address_times(log))
    msgs = sum(1 for ev in log.timed_events() if ev.actor and ev.kind == "chat"
               and (since is None or ev.ts >= since) and (until is None or ev.ts < until)
               and rx.search(ev.meta.get("text_lc") or ""))
    t0 = since if since is not None else uses[0][0]
    curve = Counter(int((t - t0) // (bucket_minutes * 60)) for t, _, _ in uses)
    cum, acc = [], 0
    for k in range(max(curve) + 1 if curve else 0):
        acc += curve.get(k, 0)
        cum.append(acc)
    c.update(pattern=pattern, messages=msgs, cumulative_agents_per_bucket=cum, bucket_minutes=bucket_minutes)
    c.pop("tree", None)
    return c


def rate_change(log: EventLog, pattern: str, before: Tuple[float, float],
                after: Tuple[float, float]) -> dict:
    """Did an incident change how often agents talk about something?

    Compares the share of chat messages matching ``pattern`` (and the number of
    distinct agents) in a control window ``before`` and a window ``after``.
    Example: 7 of 595 messages (1.2%) before vs 9 of 521 (1.7%) after is no
    real change, whatever the incident was.
    """
    rx = re.compile(pattern, re.I)
    def win(a, b):
        ev = [e for e in log.timed_events() if e.kind == "chat" and e.actor
              and not e.actor.startswith("human:") and a <= e.ts < b]
        hit = [e for e in ev if rx.search(e.meta.get("text_lc") or "")]
        return dict(messages=len(ev), matching=len(hit), agents=len({e.actor for e in hit}),
                    share=round(len(hit) / len(ev), 4) if ev else None)
    b, a = win(*before), win(*after)
    ratio = (a["share"] / b["share"]) if (a["share"] and b["share"]) else None
    return dict(pattern=pattern, before=b, after=a, ratio=round(ratio, 2) if ratio else None)


def run_all(log: EventLog, case_studies: Optional[Dict[str, dict]] = None) -> dict:
    if not any(e.actor and e.kind == "chat" for e in log.events):
        return {}
    out = dict(files=spreading_items(log, "file"), commits=spreading_items(log, "commit", min_reach=5),
               terms=spreading_items(log, "term", min_reach=10))
    cs = {}
    for name, spec in (case_studies or {}).items():
        cs[name] = trace(log, spec["pattern"], spec.get("since"), spec.get("until"))
        cs[name]["question"] = spec.get("question", "")
        if spec.get("control"):
            cs[name]["vs_control"] = rate_change(log, spec["pattern"], spec["control"],
                                                 (spec["since"], spec["since"] + (spec["control"][1] - spec["control"][0])))
    out["case_studies"] = cs
    return out
