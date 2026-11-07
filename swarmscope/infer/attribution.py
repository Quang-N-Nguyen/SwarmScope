"""Who wrote an unsigned event? Label propagation on the evidence graph.

Idea in plain steps (Zhu & Ghahramani, 2002, "label propagation"):

1. Start with the events we can name (the agent signed a board token).
   Only names signed in 2+ different payloads may spread (``corroborated``).
2. Each unnamed event looks at its linked neighbours (see ``links``). Every
   named neighbour votes for its name, with the weight of the link.
3. If one name gets at least ``min_share`` of the votes and enough total
   weight, the event takes that name, marked as *inferred*.
4. Repeat for a few rounds, so names can travel along short paths.

Small example: an unsigned event links to three named events. Two say
URI23816D with weights 0.91 and 0.42, one says KVX61677 with weight 0.42.
URI23816D has 1.33 of 1.75 votes = 76%. With ``min_share=0.8`` the event
stays unnamed; with 0.7 it becomes URI23816D (inferred).

We also group events into **personas**: clusters that are joined by very rare
identifiers or the same decode chain. A persona is one probable author even
when nobody knows its name.

Accuracy is measured by hiding the names of some signed events (whole decode
chains at a time, so a chain cannot give away its own answer), running the
propagation, and checking the guesses (``evaluate``).
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from ..events import EventLog
from .links import Links


def propagate(links: Links, seeds: Dict[int, Tuple[str, float]], rounds: int = 3,
              min_share: float = 0.8, min_weight: float = 0.4) -> Dict[int, Tuple[str, float]]:
    """Spread names from ``seeds`` ({index: (name, confidence)}) over ``links``.

    Returns {index: (name, confidence)} for newly named events only.
    """
    known: Dict[int, Tuple[str, float]] = dict(seeds)
    new: Dict[int, Tuple[str, float]] = {}
    frontier = set()
    for i in known:
        for j, _ in links.nbr[i]:
            if j not in known:
                frontier.add(j)
    for r in range(rounds):
        added = {}
        for i in frontier:
            votes: Counter = Counter()
            for j, w in links.nbr[i]:
                if j in known:
                    name, conf = known[j]
                    votes[name] += w * conf
            if not votes:
                continue
            total = sum(votes.values())
            name, top = votes.most_common(1)[0]
            if top / total >= min_share and top >= min_weight:
                # confidence: share of the vote, discounted for each hop
                added[i] = (name, round((top / total) * (0.9 ** r), 3))
        if not added:
            break
        known.update(added)
        new.update(added)
        frontier = set()
        for i in added:
            for j, _ in links.nbr[i]:
                if j not in known:
                    frontier.add(j)
    return new


def _seeds(log: EventLog, min_conf: float = 0.0) -> Dict[int, Tuple[str, float]]:
    return {i: (e.actor, e.actor_conf or 0.5) for i, e in enumerate(log.events)
            if e.actor and e.actor_conf >= min_conf}


def corroborated(seeds: Dict[int, Tuple[str, float]], links: Links,
                 min_payloads: int = 2) -> Dict[int, Tuple[str, float]]:
    """Keep only names signed in at least ``min_payloads`` different payloads.

    Why: one signed event can otherwise spread its name over a large region of
    the graph with nothing to back it up. (On Swarm Traces, one handle with a
    single signed event was given to 163 other events.) Names with one signed
    payload stay on that payload only.
    """
    roots: Dict[str, set] = defaultdict(set)
    for i, (name, _) in seeds.items():
        roots[name].add(links.root[i])
    return {i: v for i, v in seeds.items() if len(roots[v[0]]) >= min_payloads}


def evaluate(log: EventLog, links: Links, folds: int = 5, seed: int = 0,
             **kw) -> dict:
    """Grouped k-fold test: hide whole decode chains of named events, guess them.

    Reports two ground truths: all signed events, and only "write" events
    (where the handle is most likely the author, ``actor_conf >= 0.8``).
    """
    seeds_all = _seeds(log)
    roots = sorted({links.root[i] for i in seeds_all})
    rng = random.Random(seed)
    rng.shuffle(roots)
    res = {"all": [0, 0, 0], "write": [0, 0, 0]}   # [held, guessed, correct]
    for f in range(folds):
        hold = set(roots[f::folds])
        train = {i: v for i, v in seeds_all.items() if links.root[i] not in hold}
        guess = propagate(links, corroborated(train, links), **kw)
        for i, (name, conf) in seeds_all.items():
            if links.root[i] not in hold:
                continue
            for key in ("all", "write"):
                if key == "write" and log.events[i].actor_conf < 0.8:
                    continue
                res[key][0] += 1
                if i in guess:
                    res[key][1] += 1
                    res[key][2] += int(guess[i][0] == name)
    out = {}
    for key, (held, guessed, correct) in res.items():
        out[key] = dict(held_out=held, guessed=guessed, correct=correct,
                        coverage=round(guessed / held, 3) if held else None,
                        precision=round(correct / guessed, 3) if guessed else None)
    return out


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[a] = b


def personas(log: EventLog, links: Links, min_weight: float = 0.6) -> Dict[int, int]:
    """Cluster events joined by strong links (chain, or identifier in <=4 events).

    ``min_weight=0.6`` keeps identifiers shared by at most 4 events
    (1/log(5) = 0.62). Returns {index: cluster id}.
    """
    uf = _UF(len(log.events))
    for i, nb in enumerate(links.nbr):
        for j, w in nb:
            if w >= min_weight and i < j:
                uf.union(i, j)
    return {i: uf.find(i) for i in range(len(log.events))}


def bcubed(log: EventLog, clusters: Dict[int, int]) -> dict:
    """B-cubed precision/recall of clusters against signed names (Bagga & Baldwin, 1998)."""
    lab = {i: e.actor for i, e in enumerate(log.events) if e.actor}
    by_c = defaultdict(list)
    by_l = defaultdict(list)
    for i, l in lab.items():
        by_c[clusters[i]].append(i)
        by_l[l].append(i)
    p = r = 0.0
    for i, l in lab.items():
        c = by_c[clusters[i]]
        p += sum(1 for j in c if lab[j] == l) / len(c)
        r += sum(1 for j in by_l[l] if clusters[j] == clusters[i]) / len(by_l[l])
    n = len(lab) or 1
    return dict(precision=round(p / n, 3), recall=round(r / n, 3))


def run(log: EventLog, links: Links, **kw) -> dict:
    """Infer authors for the whole log and write them onto the events."""
    n = len(log.events)
    seeds = _seeds(log)
    guess = propagate(links, corroborated(seeds, links), **kw)
    for i, (name, conf) in guess.items():
        log.events[i].actor_inferred = name
        log.events[i].actor_inferred_conf = conf

    # personas
    clusters = personas(log, links)
    members = defaultdict(list)
    for i, c in clusters.items():
        members[c].append(i)
    persona_names = {}
    k = 0
    multi_handle = []
    for c, idx in members.items():
        if len(idx) < 2:
            continue
        names = Counter(log.events[i].who() for i in idx if log.events[i].who())
        signed = {log.events[i].actor for i in idx if log.events[i].actor}
        if len(signed) >= 2:
            multi_handle.append(sorted(signed))
        if names:
            persona_names[c] = names.most_common(1)[0][0]
        else:
            k += 1
            persona_names[c] = f"P{k:05d}"
    for c, idx in members.items():
        if c in persona_names:
            for i in idx:
                log.events[i].persona = persona_names[c]

    named_obs = sum(1 for e in log.events if e.actor)
    named_inf = len(guess)
    in_persona = sum(1 for e in log.events if e.persona)
    # Personas that join 2+ different payloads (not just one payload and its
    # own decoded layers). These carry real "same author" information.
    multi = sum(len(idx) for c, idx in members.items()
                if c in persona_names and len({links.root[i] for i in idx}) >= 2)
    anon = sum(1 for v in persona_names.values() if v.startswith("P"))
    return dict(
        events=n,
        named_observed=named_obs,
        named_inferred=named_inf,
        named_total_frac=round((named_obs + named_inf) / n, 4),
        named_observed_frac=round(named_obs / n, 4),
        agents_observed=len({e.actor for e in log.events if e.actor}),
        agents_with_inferred_events=len({nm for nm, _ in guess.values()}),
        events_in_personas=in_persona,
        events_in_personas_frac=round(in_persona / n, 4),
        events_in_multi_payload_personas=multi,
        events_in_multi_payload_personas_frac=round(multi / n, 4),
        anonymous_personas=anon,
        anonymous_personas_ge5=sum(1 for c, v in persona_names.items()
                                   if v.startswith("P") and len(members[c]) >= 5),
        persona_bcubed=bcubed(log, clusters),
        personas_joining_several_handles=multi_handle[:25],
        n_personas_joining_several_handles=len(multi_handle),
    )
