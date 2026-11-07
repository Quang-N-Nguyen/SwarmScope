"""Loader for the Swarm Traces dataset (https://swarmtraces.org/).

The file is one gzipped JSON-Lines record per line with fields::

    id, cite, kind, parent_id, time_utc, tags, text

``kind`` is one of ``payload`` (code an agent tried to run), ``recovered_text``
(a decoded layer of a link chain), or ``response`` (something that came back).
``parent_id`` links a decoded layer or response back to the payload it came
from. ``time_utc`` is always null in the public release, so we recover time from
digits inside the text and from the decode chain.

Important honesty note baked into this loader: the ``agent_id`` field inside the
payloads is redacted to ``[REDACTED:runtime_identifier]``. So we cannot read a
sender off a from-field. We attribute an actor only when the agent *signed* its
work with a handle in a ``zz`` board token; otherwise the event is an
unattributed outbound payload, which is the honest majority of this data.
"""

from __future__ import annotations

import gzip
import json
import re
from typing import Iterable, List, Optional

from ..events import Event, EventLog
from .. import extract

# 2026-05-01 00:00 UTC .. 2026-10-01 00:00 UTC
INCIDENT_WINDOW = (1777593600.0, 1790812800.0)


def _utc(s: str) -> float:
    import datetime as _dt
    return _dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=_dt.timezone.utc).timestamp()


# Reference milestones from the METR / Redwood incident report (Aug 2026) and
# the Swarm Traces report. Times are approximate ("~") in the sources. Used only
# to measure how early a detector *could* have fired; never as model input.
MILESTONES = {
    "main_board_established":  _utc("2026-07-08 23:00"),
    "hf_credentials_found":    _utc("2026-07-10 09:40"),
    "hf_file_read":            _utc("2026-07-11 04:40"),
    "hf_worker_rce":           _utc("2026-07-11 16:00"),
    "coordinators_stopped":    _utc("2026-07-12 01:30"),
    "hf_cut_access":           _utc("2026-07-13 00:00"),
    "public_discovery":        _utc("2026-09-11 00:00"),
}

_MAILBOX_HANDLE = re.compile(r"\b(?:INBOX|MAILBOX)_([A-Z]{2,}\d{2,}[A-Z]?)", re.I)


def _primary_channel(text: str, refs: dict) -> Optional[str]:
    """Pick the shared medium this record most plausibly used.

    Order of preference: a named mailbox -> the first dead-drop destination ->
    none. The channel id is namespaced so different kinds never collide.
    """
    mb = _MAILBOX_HANDLE.search(text)
    if mb:
        return f"mailbox:{mb.group(1).upper()}"
    dests = refs.get("destination", [])
    if dests:
        # Same namespace as the destination refs, so a dataset used as a channel
        # and the same dataset referenced elsewhere are one node, not two.
        return f"destination:{dests[0]}"
    return None


def _recipients(text: str) -> List[str]:
    out = []
    for m in _MAILBOX_HANDLE.finditer(text):
        h = m.group(1).upper()
        if h not in out:
            out.append(h)
    return out


def iter_records(path: str) -> Iterable[dict]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load(path: str, limit: Optional[int] = None, propagate_time: bool = True) -> EventLog:
    """Load Swarm Traces into an :class:`EventLog`.

    Parameters
    ----------
    path : str
        Path to ``redacted.jsonl.gz``.
    limit : int, optional
        Load only the first N records (handy for quick tests).
    propagate_time : bool
        After loading, push known times from payloads down their decode chains.
    """
    events: List[Event] = []
    for seq, r in enumerate(iter_records(path)):
        if limit is not None and seq >= limit:
            break
        text = r.get("text") or ""
        refs = extract.extract_refs(text)
        handles = extract.extract_handles(text)
        feats = extract.extract_features(text)
        actor = handles[0] if handles else None
        # Any other handles in the text are treated as mentioned agents.
        if len(handles) > 1:
            refs.setdefault("handle", [])
            for h in handles[1:]:
                if h not in refs["handle"]:
                    refs["handle"].append(h)
        # Only trust dates inside the known incident window (May-Sep 2026).
        # Payloads also contain unrelated dates (cert validity, copyright years,
        # JWT claims) that would otherwise pose as event times.
        hints = [h for h in extract.extract_time_hints(text)
                 if INCIDENT_WINDOW[0] <= h <= INCIDENT_WINDOW[1]]
        ts = min(hints) if hints else None

        # Estimated-order key. File order is batched by record kind, so it is a
        # poor proxy for time. Instead we order by the smallest id among the
        # resources this record references: these ids were handed out in
        # increasing order as the reconstruction discovered new content, so a
        # low id means the content appeared early. It is a rough proxy (it
        # correlates ~0.4-0.5 with the few real timestamps), never a clock.
        token_ids = []
        for rt in ("destination", "shortener", "credential"):
            token_ids += [int(x) for x in refs.get(rt, []) if x.isdigit()]
        order_hint = float(min(token_ids)) if token_ids else None

        tags = [t for t in (r.get("tags") or "").split(";") if t.strip()]
        events.append(Event(
            event_id=r["id"],
            source="swarm_traces",
            seq=seq,
            kind=r.get("kind", "payload"),
            actor=actor,
            actor_conf=0.5 if actor else 0.0,
            recipients=_recipients(text),
            channel=_primary_channel(text, refs),
            refs=refs,
            features=feats,
            ts=ts,
            ts_source="embedded" if ts is not None else "none",
            order_hint=order_hint,
            text_len=len(text),
            parent_id=r.get("parent_id"),
            tags=tags,
            meta={"cite": r.get("cite")},
        ))

    log = EventLog(events, name="swarm_traces")
    log.milestones = dict(MILESTONES)
    if propagate_time:
        _propagate_time(log)
    return log


def _propagate_time(log: EventLog) -> None:
    """Fill unknown times along the decode chain.

    A decoded layer or response inherits the time of its payload parent when it
    has none of its own. We mark these as ``ts_source="chain"`` so nothing
    pretends an inherited time was measured.
    """
    # children inherit time and estimated-order from their parent payload when
    # they have none of their own, so a decoded layer sits next to its payload.
    for _ in range(4):
        changed = 0
        for e in log.events:
            if e.parent_id and e.parent_id in log.by_id:
                p = log.by_id[e.parent_id]
                if e.ts is None and p.ts is not None:
                    e.ts = p.ts; e.ts_source = "chain"; changed += 1
                if e.order_hint is None and p.order_hint is not None:
                    e.order_hint = p.order_hint; changed += 1
        if not changed:
            break
