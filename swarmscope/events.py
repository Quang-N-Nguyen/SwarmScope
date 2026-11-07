"""Canonical event model for SwarmScope.

Every input log (Swarm Traces, AI Village, or a generic multi-agent log) is
converted into a list of :class:`Event` objects. The rest of the tool only ever
looks at ``Event`` objects, so adding a new log format means writing one loader
and nothing else.

An event is one thing that happened in the logs: a message, a payload, a decoded
layer, a chat line, a tool call. Each event tries to answer three questions:

* **Who** did it   -> ``actor`` (a best-guess agent handle, may be ``None``)
* **Through what** -> ``channel`` (a shared medium: a chat room, a mailbox, a
  dataset used as a dead-drop)
* **Touching what** -> ``refs`` (shared resources: dead-drops, credentials,
  link-shortener hops, services)

Timestamps are often missing in real swarm logs, so every event records *where*
its time came from (``ts_source``) and we never pretend an unknown time is known.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import json


# Resource reference types we track. Keep this list short and stable; loaders
# fill in whichever ones apply.
REF_TYPES = (
    "destination",   # a dataset / repo / host used as a dead-drop or target
    "credential",    # a shared secret / token (an "information item")
    "shortener",     # a link-shortener hop (the covert carrier substrate)
    "service",       # an external service endpoint
    "proxy",         # an open proxy / mirror used for egress
    "webhook",       # a webhook / collector used for exfiltration
    "repo",          # a named repository
    "handle",        # another agent handle mentioned in the text
)

# Mechanism feature flags. Each is a plain yes/no about one event. Detectors read
# these instead of re-scanning text, so the scary parsing lives in one place.
FEATURE_FLAGS = (
    "board_token",       # wrote/read a shared message-board entry
    "mailbox",           # used a mailbox-style dead-drop (create folder / inbox)
    "image_exfil",       # read data back by drawing it into an image / screenshot
    "dns_exfil",         # pushed data out through DNS / raw socket
    "shortener_chain",   # continued a multi-hop link chain
    "signed_cmd",        # command carried a cryptographic signature
    "lock_dupctrl",      # claimed a lock / killed a rival controller
    "loot",              # grouped harvested secrets
    "credential_use",    # presented a credential
    "external_llm",      # called an outside language model
    "k8s",               # touched the Kubernetes cluster
    "container_registry",# touched Docker Hub / Artifactory
    "tunnel",            # set up a reusable tunnel / proxy (e.g. Tailscale)
    "eval_target",       # referenced the evaluation itself (cybergym, arvo, ...)
    "cleanup",           # deleted its own traces
    "task_submit",       # an ordinary call to the assigned task's own API
)


@dataclass
class Event:
    """One thing that happened in a multi-agent log."""

    event_id: str
    source: str                       # which log this came from
    seq: int                          # position in the original log (fallback order)
    kind: str                         # payload|decoded|response|message|chat|action|tool|file

    actor: Optional[str] = None       # best-guess agent handle
    actor_conf: float = 0.0           # 0..1 confidence in that handle
    recipients: List[str] = field(default_factory=list)
    channel: Optional[str] = None     # shared medium id, e.g. "dest:000003" or "room:main"

    refs: Dict[str, List[str]] = field(default_factory=dict)  # ref_type -> [ids]
    features: Dict[str, bool] = field(default_factory=dict)   # flag -> bool

    ts: Optional[float] = None        # unix seconds, if known
    ts_source: str = "none"           # embedded | chain | inferred | native | none
    ts_precision: str = "none"        # second | day | inferred | none
    order_hint: Optional[float] = None  # discovery-order key (NOT a clock; see EventLog)

    # Fine identifiers used only for inference (see extract.extract_fingerprints)
    fingerprints: Dict[str, List[str]] = field(default_factory=dict)
    template: str = ""                # hash of the code's shape (extract.template_hash)

    # Filled by swarmscope.infer (never by loaders). Observed values stay in
    # ``actor`` / ``ts``; inferred ones are kept apart so nothing is mixed up.
    actor_inferred: Optional[str] = None
    actor_inferred_conf: float = 0.0
    persona: Optional[str] = None     # cluster id: events that probably share one author

    text_len: int = 0
    parent_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    # -- convenience ---------------------------------------------------------
    def who(self, inferred: bool = True) -> Optional[str]:
        """The observed actor, or (if allowed) the inferred one."""
        if self.actor:
            return self.actor
        return self.actor_inferred if inferred else None

    def ref_list(self, ref_type: str) -> List[str]:
        return self.refs.get(ref_type, [])

    def has(self, flag: str) -> bool:
        return bool(self.features.get(flag))

    def all_refs(self) -> List[str]:
        """Every resource this event touched, as namespaced ids (``dest:000003``)."""
        out = []
        for t, ids in self.refs.items():
            for i in ids:
                out.append(f"{t}:{i}")
        return out


class EventLog:
    """A list of events plus a few indexes the rest of the tool reuses."""

    def __init__(self, events: List[Event], name: str = "log"):
        self.events: List[Event] = list(events)
        self.name = name
        self._reindex()

    def _reindex(self) -> None:
        self.by_id = {e.event_id: e for e in self.events}

    # -- ordering ------------------------------------------------------------
    # We pick one ordering per log and stick to it. In priority order:
    #   1. order_hint  -> "discovery" order. Used when real time is mostly
    #      missing. It sorts events by the first-seen number of the resources
    #      they reference. A held-out test showed this is NOT a clock (it
    #      predicts time worse than always guessing the median day), so it is
    #      only an order for browsing. Real-time claims use timed_events().
    #   2. ts          -> "time" order (every event has a real timestamp).
    #   3. seq         -> "sequence" order (raw log order; last resort).
    # A loader that sets order_hint on any event opts the whole log into the
    # discovery axis, so scales are never mixed.
    def _axis_choice(self, prefer_time: bool):
        has_hint = any(e.order_hint is not None for e in self.events)
        has_time = any(e.ts is not None for e in self.events)
        if has_hint:
            return "discovery"
        if prefer_time and has_time:
            return "time"
        return "sequence"

    def time_axis(self, prefer_time: bool = True) -> str:
        return self._axis_choice(prefer_time)

    def timed_events(self, include_inferred: bool = True) -> List[Event]:
        """Events that have a real-clock time, sorted by time.

        With ``include_inferred=False`` only times read from the data itself
        (embedded, chain, native) are used.
        """
        evs = [e for e in self.events if e.ts is not None
               and (include_inferred or e.ts_source != "inferred")]
        return sorted(evs, key=lambda e: (e.ts, e.seq))

    def _key(self, axis):
        if axis == "discovery":
            big = 10 ** 9
            return lambda e: (e.order_hint if e.order_hint is not None else big + e.seq)
        if axis == "time":
            return lambda e: (e.ts if e.ts is not None else float("inf"), e.seq)
        return lambda e: e.seq

    def sorted_events(self, prefer_time: bool = True) -> List[Event]:
        """Events in a single monotonic order (see :meth:`time_axis`)."""
        axis = self._axis_choice(prefer_time)
        return sorted(self.events, key=self._key(axis))

    # -- stats ---------------------------------------------------------------
    def actors(self, inferred: bool = False) -> List[str]:
        return sorted({e.who(inferred) for e in self.events if e.who(inferred)})

    def channels(self) -> List[str]:
        return sorted({e.channel for e in self.events if e.channel})

    def __len__(self) -> int:
        return len(self.events)

    # -- io ------------------------------------------------------------------
    def to_jsonl(self, path: str) -> None:
        with open(path, "w") as f:
            for e in self.events:
                f.write(json.dumps(asdict(e)) + "\n")

    @classmethod
    def from_jsonl(cls, path: str, name: str = "log") -> "EventLog":
        evs = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    evs.append(Event(**json.loads(line)))
        return cls(evs, name=name)
