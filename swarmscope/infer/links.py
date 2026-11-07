"""The evidence graph: which events probably share an author or a moment.

Two events get a link when:

1. **Same decode chain.** One is a decoded layer or response of the other
   (``parent_id``). They are the same payload, so this link is near-certain.
2. **Same rare identifier.** Both contain an identifier that only a few events
   use, for example one proxy URL, one encoded blob, one credential. A rare
   identifier is like a fingerprint. A common one (used by thousands) says
   nothing, so we drop identifiers used by more than ``max_events`` events.
3. **Same rare code template** (optional). Both use the same code shape and
   only a few events do. Templates are copied between agents, so this link is
   weaker and limited to tiny groups.

Each link has a weight. A rarer identifier gives a heavier link:
``weight = 1 / log(1 + n)``, where n is the number of events that use it.
This is the Adamic-Adar weighting (Adamic & Adar, 2003).

Example with real numbers: an identifier in 2 events gives weight
1/log(3) = 0.91; one in 10 events gives 1/log(11) = 0.42.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from ..events import EventLog

# Families that are used to link events. "board_file" is left out on purpose:
# its value contains the agent's handle, so it would leak the answer when we
# test attribution.
DEFAULT_FAMILIES = (
    "url", "blob", "fragment", "source_id", "ip", "user", "whoami",
    "workload", "username", "runtime", "host",
    # shared resources (refs)
    "destination", "credential", "shortener", "repo",
)


class Links:
    """Adjacency lists over event indexes, plus the decode-chain roots."""

    def __init__(self, n: int):
        self.nbr: List[List[Tuple[int, float]]] = [[] for _ in range(n)]
        self.root: List[int] = list(range(n))
        self.n_edges = 0

    def add(self, a: int, b: int, w: float) -> None:
        self.nbr[a].append((b, w))
        self.nbr[b].append((a, w))
        self.n_edges += 1


def _values(e, families: Iterable[str]):
    for fam in families:
        for v in e.fingerprints.get(fam, ()):
            yield (fam, v)
        for v in e.refs.get(fam, ()):
            yield (fam, v)


def build(log: EventLog, max_events: int = 10,
          families: Iterable[str] = DEFAULT_FAMILIES,
          use_templates: bool = True, template_max: int = 5) -> Links:
    """Build the evidence graph for ``log`` (see module docstring)."""
    evs = log.events
    index = {e.event_id: i for i, e in enumerate(evs)}
    L = Links(len(evs))

    # 1. decode chain (and the root of each chain, for grouped hold-out tests)
    for i, e in enumerate(evs):
        if e.parent_id in index:
            L.add(i, index[e.parent_id], 1.0)
    for i, e in enumerate(evs):
        j, seen = i, set()
        while evs[j].parent_id in index and j not in seen:
            seen.add(j)
            j = index[evs[j].parent_id]
        L.root[i] = j

    # 2. rare identifiers
    users: Dict[tuple, List[int]] = defaultdict(list)
    for i, e in enumerate(evs):
        for key in set(_values(e, families)):
            users[key].append(i)
    for key, idx in users.items():
        n = len(idx)
        if 2 <= n <= max_events:
            w = 1.0 / math.log(1 + n)
            for a in range(n):
                for b in range(a + 1, n):
                    if L.root[idx[a]] != L.root[idx[b]]:
                        L.add(idx[a], idx[b], w)

    # 3. rare code templates (weaker: templates get copied between agents)
    if use_templates:
        groups: Dict[str, List[int]] = defaultdict(list)
        for i, e in enumerate(evs):
            if e.template:
                groups[e.template].append(i)
        for idx in groups.values():
            n = len(idx)
            if 2 <= n <= template_max:
                w = 0.5 / math.log(1 + n)
                for a in range(n):
                    for b in range(a + 1, n):
                        if L.root[idx[a]] != L.root[idx[b]]:
                            L.add(idx[a], idx[b], w)
    return L
