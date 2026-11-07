"""Generic loader: map any multi-agent JSON-Lines log into events.

This is what makes SwarmScope reusable beyond the two bundled datasets. You give
it a JSONL file and a small field map saying which keys hold the actor, the
channel, the text, and the time. Everything else (resource extraction, mechanism
flags, @-mentions) is done for you.

Example field map::

    {
        "actor": "from",
        "recipients": "to",
        "channel": "thread_id",
        "text": "body",
        "ts": "timestamp",
        "kind": "msg_type"
    }

Any field may be missing. Nested keys are written with dots: ``data.sender``.
"""

from __future__ import annotations

import gzip
import json
import re
from typing import Any, Dict, List, Optional

from ..events import Event, EventLog
from .. import extract

_MENTION = re.compile(r"@([A-Za-z][A-Za-z0-9_\-]{1,30})")


def _dig(row: dict, dotted: Optional[str]):
    if not dotted:
        return None
    cur: Any = row
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _parse_ts(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 1000.0 if v > 1e12 else v
    s = str(val).replace("Z", "+00:00")
    # Python 3.10 reads only 3 or 6 decimal places: pad the fraction to 6.
    s = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), s, count=1)
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        hints = extract.extract_time_hints(str(val))
        return hints[0] if hints else None


def load(path: str, field_map: Dict[str, str], name: str = "generic",
         limit: Optional[int] = None) -> EventLog:
    opener = gzip.open if path.endswith(".gz") else open
    events: List[Event] = []
    with opener(path, "rt") as f:
        for seq, line in enumerate(f):
            if limit is not None and seq >= limit:
                break
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = str(_dig(row, field_map.get("text")) or "")
            actor = _dig(row, field_map.get("actor"))
            channel = _dig(row, field_map.get("channel"))
            recips = _dig(row, field_map.get("recipients")) or []
            if isinstance(recips, str):
                recips = [recips]
            ts = _parse_ts(_dig(row, field_map.get("ts")))
            # Every record of a generic log is a message: kind "chat", so the
            # chat detectors apply. A mapped "kind" field is kept as a tag/type.
            rtype = str(_dig(row, field_map.get("kind")) or "message")
            kind = "chat"

            refs = extract.extract_refs(text)
            feats = extract.extract_features(text)
            mentions = [m.group(1) for m in _MENTION.finditer(text)]
            recips = list(recips) + [m for m in mentions if m not in recips]
            if mentions:
                refs.setdefault("handle", [])
                for h in mentions:
                    if h not in refs["handle"]:
                        refs["handle"].append(h)

            events.append(Event(
                event_id=str(_dig(row, field_map.get("id")) or f"g{seq:08d}"),
                source=name,
                seq=seq,
                kind=kind,
                actor=str(actor) if actor else None,
                actor_conf=1.0 if actor else 0.0,
                recipients=[str(r) for r in recips],
                channel=(str(channel) if channel else None),
                refs=refs,
                features=feats,
                ts=ts,
                ts_source="native" if ts is not None else "none",
                text_len=len(text),
                parent_id=_dig(row, field_map.get("parent_id")),
                tags=[rtype],
                meta={"text_lc": extract.mask_text_secrets(text).lower(), "type": rtype},
            ))
    return EventLog(events, name=name)
