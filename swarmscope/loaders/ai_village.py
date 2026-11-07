"""Loader for the AI Village dataset (https://huggingface.co/datasets/aidigestorg/ai-village).

The dataset is gated: a user must log in to Hugging Face and accept the
``ai-village-research-terms`` before the files can be downloaded. Use
``scripts/download_ai_village.py`` to fetch it once you have access.

Unlike Swarm Traces, AI Village is *attributed*: every chat line has a speaker
and a room. So the event model is much cleaner here -- ``actor`` is the speaker,
``channel`` is the room, and recipients come from @-mentions. This loader reads
either the single ``village-transcript.json`` (recommended) or the pair
``chat_messages.jsonl.gz`` + ``events.jsonl.gz``.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from typing import List, Optional

from ..events import Event, EventLog
from .. import extract

_MENTION = re.compile(r"@([A-Za-z][A-Za-z0-9_\-]{1,30})")


def _parse_ts(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 1000.0 if v > 1e12 else v
    s = str(val).replace("Z", "+00:00")
    try:
        import datetime as _dt
        return _dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _mk_event(seq: int, speaker, room, content, ts, kind, extra=None) -> Event:
    content = content or ""
    refs = extract.extract_refs(content)
    feats = extract.extract_features(content)
    mentions = [m.group(1) for m in _MENTION.finditer(content)]
    if mentions:
        refs.setdefault("handle", [])
        for h in mentions:
            if h not in refs["handle"]:
                refs["handle"].append(h)
    return Event(
        event_id=f"av{seq:08d}",
        source="ai_village",
        seq=seq,
        kind=kind,
        actor=str(speaker) if speaker else None,
        actor_conf=1.0 if speaker else 0.0,          # AI Village is attributed
        recipients=mentions,
        channel=(f"room:{room}" if room else None),
        refs=refs,
        features=feats,
        ts=_parse_ts(ts),
        ts_source="native" if ts is not None else "none",
        text_len=len(content),
        parent_id=None,
        tags=[],
        meta=extra or {},
    )


def load_transcript(path: str, limit: Optional[int] = None) -> EventLog:
    """Load the single ``village-transcript.json`` file.

    The file is a JSON array (or an object with an ``events``/``messages`` key)
    of chat and activity entries. We read speaker, room, content, and timestamp
    with a few common field-name fallbacks so small schema drifts do not break
    the loader.
    """
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        for key in ("events", "messages", "transcript", "data"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
    events: List[Event] = []
    for seq, row in enumerate(data):
        if limit is not None and seq >= limit:
            break
        if not isinstance(row, dict):
            continue
        speaker = row.get("speaker") or row.get("agent") or row.get("agent_name") or row.get("author")
        room = row.get("room") or row.get("channel") or row.get("chat_room")
        content = row.get("content") or row.get("text") or row.get("message") or ""
        ts = row.get("timestamp") or row.get("created_at") or row.get("time")
        kind = row.get("actionType") or row.get("type") or "chat"
        events.append(_mk_event(seq, speaker, room, content, ts, str(kind).lower()))
    return EventLog(events, name="ai_village")


def load_chat_messages(path: str, limit: Optional[int] = None) -> EventLog:
    """Load ``chat_messages.jsonl.gz`` (room, speaker, content, timestamp)."""
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
            events.append(_mk_event(
                seq,
                row.get("speaker"), row.get("room"),
                row.get("content"), row.get("timestamp"),
                "chat",
            ))
    return EventLog(events, name="ai_village")


def load(path: str, limit: Optional[int] = None) -> EventLog:
    """Load AI Village from a folder, a transcript file, or a chat file.

    * a ``.json`` file  -> treated as ``village-transcript.json``
    * a ``chat_messages`` file -> that chat table
    * a folder -> prefers ``village-transcript.json``, else ``chat_messages.jsonl.gz``
    """
    if os.path.isdir(path):
        tj = os.path.join(path, "village-transcript.json")
        cm = os.path.join(path, "chat_messages.jsonl.gz")
        if os.path.exists(tj):
            return load_transcript(tj, limit)
        if os.path.exists(cm):
            return load_chat_messages(cm, limit)
        raise FileNotFoundError(f"No AI Village files found in {path}")
    if path.endswith(".json"):
        return load_transcript(path, limit)
    return load_chat_messages(path, limit)
