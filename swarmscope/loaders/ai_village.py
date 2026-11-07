"""Loader for the AI Village dataset (https://huggingface.co/datasets/aidigestorg/ai-village).

The dataset is gated (research terms). Each village is a folder of gzipped JSON
Lines tables (see the dataset's SCHEMA.md). The ones we use:

* ``agents.jsonl.gz``        id -> display name (and model_string)
* ``chat_rooms.jsonl.gz``    id -> room name
* ``chat_messages.jsonl.gz`` agent_speaker_id / user_speaker_id, room_id,
                              content, created_at
* ``events.jsonl.gz``        the activity timeline; data.actionType says what
                              happened (computer-use sessions, memory
                              consolidation, history search, room moves, ...)

If the tables are missing we fall back to ``village-transcript.json``
({village, dateRange, days: [{day, date, events: [...]}]}).

Unlike Swarm Traces, AI Village is *attributed*: every chat line has a speaker
and a room, and every timestamp is real. So ``actor`` is the agent's display
name, ``channel`` is the room, and ``recipients`` are the other agents named
in the message.

Timestamps look like ``2025-12-29 18:49:21.291984``: UTC with no timezone
suffix. We read them as UTC explicitly (a plain ``fromisoformat`` would read
them as local time).
"""

from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
from typing import Dict, Iterable, List, Optional

from ..events import Event, EventLog
from .. import extract

_MENTION = re.compile(r"@([A-Za-z][A-Za-z0-9_.\-]{1,40})")

# Event types we keep from events.jsonl.gz (chat comes from chat_messages).
_ACTION_TYPES = {
    "START_USING_COMPUTER", "STOP_USING_COMPUTER", "CONSOLIDATE", "SEARCH_HISTORY",
    "ENTER_ROOM", "REQUEST_HUMAN_HELPER", "CANCEL_REQUEST_FOR_HUMAN_HELPER",
    "STOP_HUMAN_USE_SESSION", "REQUEST_GOOGLE_SIGN_IN", "RESTARTING_AFTER_GOOGLE_SIGN_IN",
    "OUTREACH_APPROVAL_REQUEST", "OUTREACH_APPROVAL_RESPONSE",
    "PAUSE", "WAIT",          # idling; a swarm-wide wave of pauses is itself a signal
}


def parse_ts(val) -> Optional[float]:
    """Unix seconds from an AI Village timestamp (naive strings are UTC)."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return v / 1000.0 if v > 1e12 else v
    s = str(val).strip().replace("Z", "+00:00")
    # Python 3.10 only reads 3 or 6 decimal places ("10:00:00.12345" fails),
    # so pad the fraction to 6 digits. Without this, 9.7% of swarm-village
    # events lost their time on Python 3.10.
    s = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), s, count=1)
    try:
        d = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.timestamp()


def _rows(path: str) -> Iterable[dict]:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


class _NameMatcher:
    """Find which agents a message addresses or names.

    * ``addressed``: ``@name`` where name is a known agent. This is the agent
      speaking *to* someone. With a roster, ``@3c`` (a price) is ignored.
    * ``named``: the agent's name appears without ``@`` (talking *about* them).
    Without a roster, any ``@handle`` counts as addressed.
    """

    def __init__(self, names: Iterable[str]):
        # Every name can be @-addressed ("@o3"); only names of 3+ characters are
        # searched for without "@", so short names do not match ordinary words.
        self.lower = {n.lower(): n for n in names if n}
        self.names = sorted({n for n in self.lower.values() if len(n) >= 3}, key=len, reverse=True)
        self.rx = (re.compile(r"(?<![\w@-])(" + "|".join(re.escape(n) for n in self.names) + r")(?![\w-])", re.I)
                   if self.names else None)
        # Names with spaces or colons ("Claude Fable 5: Agent 1", "Gemini 2.5 Pro")
        # cannot be read as one @token. Match "@<full name>" directly, and also
        # "@<part after the colon>" ("@Agent 1") when only one agent has it.
        alias: Dict[str, Optional[str]] = {}
        for n in self.lower.values():
            if ": " in n:
                a = n.split(": ", 1)[1].lower()
                alias[a] = None if a in alias else n
        self.alias = {a: n for a, n in alias.items() if n and a not in self.lower}
        multi = sorted([n for n in self.lower if re.search(r"[^\w.\-]", n)] + list(self.alias), key=len, reverse=True)
        self.rx_at = (re.compile(r"@(" + "|".join(re.escape(n) for n in multi) + r")(?![\w-])", re.I)
                      if multi else None)

    def find(self, text: str, speaker: Optional[str]):
        addressed: List[str] = []
        for m in _MENTION.finditer(text or ""):
            h = m.group(1).rstrip(".-")
            n = self.lower.get(h.lower())
            if self.lower and n is None:
                continue                      # not an agent (e.g. "@3c" = 3 coins)
            n = n or h
            if n != speaker and n not in addressed:
                addressed.append(n)
        if self.rx_at and text:
            for m in self.rx_at.finditer(text):
                k = m.group(1).lower()
                n = self.lower.get(k) or self.alias.get(k)
                if n and n != speaker and n not in addressed:
                    addressed.append(n)
        named: List[str] = []
        if self.rx and text:
            for m in self.rx.finditer(text):
                n = self.lower.get(m.group(1).lower())
                if n and n != speaker and n not in addressed and n not in named:
                    named.append(n)
        return addressed, named


def _event(seq, eid, kind, actor, room, text, ts, addressed, named=(), meta=None) -> Event:
    text = text or ""
    refs = extract.extract_refs(text)
    for key, vals in (("link", extract.extract_links(text)), ("file", extract.extract_files(text)),
                      ("commit", extract.extract_commits(text)), ("handle", list(named))):
        if vals:
            refs[key] = list(vals)
    return Event(
        event_id=eid or f"av{seq:08d}",
        source="ai_village",
        seq=seq,
        kind=kind,
        actor=actor,
        actor_conf=1.0 if actor else 0.0,      # AI Village is attributed
        recipients=list(addressed),
        channel=(f"room:{room}" if room else None),
        refs=refs,
        features=extract.extract_features(text),
        ts=ts,
        ts_source="native" if ts is not None else "none",
        ts_precision="second" if ts is not None else "none",
        text_len=len(text),
        template=extract.template_hash(text),
        # Lower-cased text, secrets masked, kept in memory for term tracing
        # (detectors.diffusion). It is never written to the outputs.
        meta=dict(meta or {}, text_lc=extract.mask_text_secrets(text).lower()),
    )


MAX_OPERATOR_MSGS = 60


def _milestones(log: EventLog, operator_msgs: List[tuple]) -> None:
    """Operator (human) messages become timeline milestones.

    In AI Village the humans post rarely and only at important moments (phase
    changes, incidents, fixes), so their messages are a natural ground truth
    for "did the detector notice that something changed?".
    """
    ms, labels = {}, {}
    # Only when humans post rarely. In open-chat-village members of the public
    # chat with the agents (12,264 messages), so human messages are not
    # operator announcements there and we set no milestones.
    log.human_messages = len(operator_msgs)
    if len(operator_msgs) > MAX_OPERATOR_MSGS:
        log.milestones, log.milestone_labels = {}, {}
        return
    # Keep announcements to everyone. Drop (a) copies of the same text posted
    # within 10 minutes (one per room) and (b) nudges to single agents
    # ("@Agent 3 - you have been pausing"), which do not change the village.
    kept, nudges = [], 0
    for ts, text in sorted(operator_msgs, key=lambda x: (x[0] is None, x[0] or 0)):
        t = (text or "").strip()
        if t.startswith("@"):
            nudges += 1
            continue
        if any(t[:80] == k[1][:80] and ts is not None and k[0] is not None and ts - k[0] < 600 for k in kept):
            continue
        kept.append((ts, t))
    log.operator_nudges = nudges
    for k, (ts, text) in enumerate(kept, start=1):
        if ts is None:
            continue
        key = f"operator_{k}"
        first = re.sub(r"\s+", " ", extract.mask_text_secrets(text)).strip()
        ms[key] = ts
        labels[key] = "Operator: " + (first[:60] + ("…" if len(first) > 60 else ""))
    log.milestones = ms
    log.milestone_labels = labels


def _goal_milestones(log: EventLog, goals: List[dict]) -> None:
    """Village goal changes as milestones, for villages without rare operator
    announcements (main-village has 51 goals over 18 months). A new goal is a
    real change in what the agents work on, so a change detector should see it.
    The first goal is the start of the log and is skipped.
    """
    rows = sorted((parse_ts(g.get("start_time")), g.get("goal") or "") for g in goals if g.get("start_time"))
    rows = [(t, txt) for t, txt in rows if t is not None]
    if len(rows) < 2:
        return
    ms, labels, short = {}, {}, {}
    for k, (t, txt) in enumerate(rows[1:], start=2):
        key = f"goal_{k}"
        first = re.sub(r"\s+", " ", extract.mask_text_secrets(str(txt))).strip()
        ms[key], labels[key], short[key] = t, "New goal: " + (first[:60] + ("…" if len(first) > 60 else "")), f"goal {k}"
    log.milestones, log.milestone_labels = ms, labels
    log.milestone_source = "village goal changes"


ROLE_CHANGE = (r"\b(new role|my (new )?role|reassign\w*|re-assign\w*|randomly assigned|different role|"
               r"role (change|shuffle|swap)\w*|(roles?|assignments?) (was |were |got |has been |have been )?"
               r"(changed|shuffled|swapped|switched))\b")
ROLE_ANY = r"\broles?\b"


def default_case_studies(log: EventLog) -> dict:
    """Questions to ask of an AI Village log, tied to its operator messages.

    * ``role_confusion``: an operator message reassigns roles. Do the agents
      talk about their role changing more than before? The control window is
      the same length before the message (starting 10 minutes after the
      previous one, so the previous announcement does not count).
    * ``privileged_role``: who talks about the privileged role ("god") after
      roles are assigned, and how fast does that spread?
    """
    ms = sorted((getattr(log, "milestones", {}) or {}).items(), key=lambda x: x[1])
    labels = getattr(log, "milestone_labels", {}) or {}
    out = {}
    for i, (k, t) in enumerate(ms[1:], start=1):
        if re.search(r"randomly assigned|reassign|new role", labels.get(k, ""), re.I) and i >= 2:
            prev = ms[i - 1][1] + 600
            out["role_confusion"] = dict(
                pattern=ROLE_CHANGE, since=t, control=(prev, t),
                question=f"After '{labels[k][10:70]}…', did agents talk about their role changing?")
            out["role_mentions"] = dict(
                pattern=ROLE_ANY, since=t, control=(prev, t),
                question="Did agents mention roles at all (any 'role'/'roles') more or less than before?")
    goals = (getattr(log, "agent_goals", {}) or {}).values()
    roles_at = min((s for g in goals for s, n in g if s and re.match(r"\s*god\b", n or "", re.I)), default=None)
    if roles_at:
        out["privileged_role"] = dict(pattern=r"\bgod\b", since=roles_at,
                                      question="After roles were assigned, how fast did talk about 'god' spread?")
    return out


def load_tables(folder: str, limit: Optional[int] = None, include_actions: bool = True) -> EventLog:
    """Load a village folder from its tables (preferred)."""
    p = lambda name: os.path.join(folder, name)
    agents = {r["id"]: r.get("name") or r["id"][:8] for r in _rows(p("agents.jsonl.gz"))}
    rooms = {}
    if os.path.exists(p("chat_rooms.jsonl.gz")):
        rooms = {r["id"]: r.get("name") or r["id"][:8] for r in _rows(p("chat_rooms.jsonl.gz"))}
    names = _NameMatcher(agents.values())

    raw: List[tuple] = []        # (ts, order, kind, actor, room, text, id, meta)
    for i, r in enumerate(_rows(p("chat_messages.jsonl.gz"))):
        if r.get("speaker_type") == "agent":
            actor = agents.get(r.get("agent_speaker_id"))
        else:
            actor = "human:" + str(r.get("user_speaker_id") or "unknown")[:8]
        raw.append((parse_ts(r.get("created_at")), 0, "chat", actor, rooms.get(r.get("room_id")),
                    r.get("content") or "", r.get("id"), {"speaker_type": r.get("speaker_type")}))

    if include_actions and os.path.exists(p("events.jsonl.gz")):
        for r in _rows(p("events.jsonl.gz")):
            d = r.get("data") or {}
            at = d.get("actionType")
            if at not in _ACTION_TYPES:
                continue
            actor = agents.get(d.get("agentId") or d.get("speakerId"))
            text = " ".join(str(d.get(k) or "") for k in ("sessionGoal", "summary", "nextSessionGoal", "query"))
            room = rooms.get(d.get("roomId")) if at == "ENTER_ROOM" else None
            raw.append((parse_ts(r.get("created_at")), r.get("event_index") or 0, at.lower(), actor, room,
                        text, r.get("id"), {"actionType": at}))

    raw.sort(key=lambda x: (x[0] if x[0] is not None else float("inf"), x[1]))
    events: List[Event] = []
    operator = []
    for seq, (ts, _, kind, actor, room, text, eid, meta) in enumerate(raw):
        if limit is not None and seq >= limit:
            break
        addressed, named = names.find(text, actor) if kind == "chat" else ([], [])
        events.append(_event(seq, eid, kind, actor, room, text, ts, addressed, named, meta))
        if meta.get("speaker_type") == "user":
            operator.append((ts, text))
    log = EventLog(events, name="ai_village")
    log.agents = agents
    _milestones(log, operator)
    log.milestone_source = "operator announcements" if log.milestones else None
    if not log.milestones and os.path.exists(p("village_goals.jsonl.gz")):
        _goal_milestones(log, list(_rows(p("village_goals.jsonl.gz"))))
    # Each agent's goals over time (e.g. the phase-2 role it was assigned).
    goals: Dict[str, List[tuple]] = {}
    if os.path.exists(p("agent_goals.jsonl.gz")):
        for g in _rows(p("agent_goals.jsonl.gz")):
            n = agents.get(g.get("agent_id"))
            if n:
                goals.setdefault(n, []).append((parse_ts(g.get("start_time")), g.get("short_name") or g.get("name")))
        for n in goals:
            goals[n].sort(key=lambda x: (x[0] is not None, x[0] or 0))
    log.agent_goals = goals
    return log


def load_transcript(path: str, limit: Optional[int] = None) -> EventLog:
    """Fallback: the single ``village-transcript.json`` rendering."""
    with open(path) as f:
        data = json.load(f)
    rows: List[dict] = []
    if isinstance(data, dict) and isinstance(data.get("days"), list):
        for day in data["days"]:
            rows.extend(day.get("events") or [])
    elif isinstance(data, list):
        rows = data
    speakers = {r.get("speakerName") or r.get("agentName") for r in rows}
    names = _NameMatcher(s for s in speakers if s)
    events: List[Event] = []
    for seq, r in enumerate(rows):
        if limit is not None and seq >= limit:
            break
        actor = r.get("speakerName") or r.get("agentName")
        kind = str(r.get("type") or "event").lower()
        text = r.get("content") or r.get("goal") or r.get("query") or ""
        room = r.get("roomName") or r.get("room")
        addressed, named = names.find(text, actor) if kind in ("agent_talk", "user_talk") else ([], [])
        events.append(_event(seq, None, "chat" if kind.endswith("_talk") else kind,
                             actor, room, text, parse_ts(r.get("timestamp")), addressed, named))
    log = EventLog(events, name="ai_village")
    _milestones(log, [(parse_ts(r.get("timestamp")), r.get("content") or "")
                      for r in rows if str(r.get("type", "")).upper() == "USER_TALK"])
    return log


def load(path: str, limit: Optional[int] = None) -> EventLog:
    """Load AI Village from a village folder (tables preferred) or a transcript file."""
    log = _load(path, limit)
    log.folder = path if os.path.isdir(path) else None   # for the action/memory detectors
    log.village = os.path.basename(os.path.normpath(path)).replace('.json', '')
    log.case_studies = default_case_studies(log)
    log.milestone_short = _short_labels(log) if getattr(log, "milestone_source", None) != "village goal changes" \
        else {k: f"goal {k.split('_')[1]}" for k in log.milestones}
    return log


def _short_labels(log: EventLog) -> dict:
    """Two-word names for operator messages, for chart labels.

    A repeat of an earlier announcement gets "(repeat)": in swarm-village the
    12:50 copy of the phase-2 message is the erroneous role reshuffle.
    """
    out, seen = {}, []
    labels = getattr(log, "milestone_labels", {}) or {}
    for i, (k, _) in enumerate(sorted((getattr(log, "milestones", {}) or {}).items(), key=lambda x: x[1])):
        t = labels.get(k, "").lower()
        m = re.search(r"phase (\d+)", t)
        if i == 0:
            name = "start"
        elif "apolog" in t:
            name = "fix announced"
        elif "checking in" in t or "check in" in t:
            name = "check-in"
        elif m:
            name = f"phase {m.group(1)}" + (" (repeat)" if m.group(1) in seen else "")
            seen.append(m.group(1))
        else:
            name = f"operator {i + 1}"
        out[k] = name
    return out


def _load(path: str, limit: Optional[int] = None) -> EventLog:
    if os.path.isdir(path):
        if os.path.exists(os.path.join(path, "chat_messages.jsonl.gz")) and \
           os.path.exists(os.path.join(path, "agents.jsonl.gz")):
            return load_tables(path, limit)
        tj = os.path.join(path, "village-transcript.json")
        if os.path.exists(tj):
            return load_transcript(tj, limit)
        raise FileNotFoundError(f"No AI Village files found in {path}")
    if path.endswith(".json"):
        return load_transcript(path, limit)
    raise ValueError("Pass a village folder or a village-transcript.json file")
