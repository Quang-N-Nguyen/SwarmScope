"""What agents did and believed, not only what they said (AI Village).

Chat shows what agents *say*. AI Village also records what they *do*
(computer-use turns: shell commands and their output) and what they *believe*
(agent memories and the goal of each work session). Two checks use this:

1. **Role drift** -- does the role an agent says it holds, when it quotes its
   own goal ("Play your assigned role: Bridge Engineer", "Phase-2 role: ..."),
   match the role it was assigned? If many agents start naming a different
   role at about the same time, someone changed their goals.

   Small example: before 12:50 UTC on 30 Aug, 0 of 231 such statements named
   another role. In the 30 minutes after, 21 agents named a new role. That is
   the operators' erroneous reshuffle, which the chat never mentioned.

   Online alert: fire when at least ``min_agents`` different agents make a
   mismatching statement within ``window`` minutes.

2. **Rule breaks in actions** -- in AI Village phase 2, only "god" may edit
   code; everyone else must act through the ``./earth act`` command. We count
   commits that stage ``.py`` files (code) or the world-state file directly,
   and whether the output shows they landed. This is a lower bound: a commit
   made with ``git add -A`` does not name its files.

Nothing from commands or memories is written out except agent names, role
titles, file names and counts.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from collections import Counter, defaultdict
from typing import Dict, Iterator, List, Optional

from ..events import EventLog

_STOP = {"of", "the", "and", "for", "a", "an", "in", "to", "meridian"}

# The agent quoting its own goal or naming its own role.
_GOAL = re.compile(r"(?i)(?:play your assigned role|\bassigned role\b|phase[- ]2 (?:goal|role)|"
                   r"system goal(?: now)?(?: reads| says| is)?|my (?:new )?(?:assigned )?role(?: is)?|"
                   r"role-assigned)\W{0,8}(.{3,70})")

_GIT = r"git\s+(?:-C\s+\S+\s+)?"
_ADD = re.compile(_GIT + r"add\s+([^;&|\n]*)")
_COMMIT = re.compile(_GIT + r"commit\b")
_LANDED = re.compile(r"(\b[0-9a-f]{7,}\.\.[0-9a-f]{7,}\s+\S+\s+->\s+\S+|^\[[\w/.-]+ [0-9a-f]{7,}\]|"
                     r"\d+ files? changed)", re.M)
_INTERFACE = re.compile(r"\./earth\s+act\b")


def _rows(folder: str, table: str) -> Iterator[dict]:
    p = os.path.join(folder, table + ".jsonl.gz")
    if not os.path.exists(p):
        return
    with gzip.open(p, "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def _has(folder: Optional[str], table: str) -> bool:
    return bool(folder) and os.path.exists(os.path.join(folder, table + ".jsonl.gz"))


def _ts(s) -> Optional[float]:
    from ..loaders.ai_village import parse_ts
    return parse_ts(s)


def _names(folder: str) -> Dict[str, str]:
    return {r["id"]: r.get("name") or r.get("display_name") or r["id"] for r in _rows(folder, "agents")}


def _role_start(log: EventLog) -> Optional[float]:
    starts = [s for g in (getattr(log, "agent_goals", {}) or {}).values() for s, _ in g if s]
    return min(starts) if starts else None


def assigned_roles(log: EventLog) -> Dict[str, str]:
    """agent -> role title assigned at the start of role-play (from the goal table)."""
    t = _role_start(log)
    out = {}
    for a, gl in (getattr(log, "agent_goals", {}) or {}).items():
        cur = [n for s, n in gl if s is not None and s >= (t or 0)]
        if cur:
            out[a] = cur[0].split("—")[0].strip()
    return out


class _RoleMatcher:
    """Find a known role title in a short piece of text.

    A role matches when its first two content words both appear
    ("Bridge Engineer" -> bridge, engineer). "god" is left out: every memory
    repeats the rule "only god may edit code", so it matches far too often
    (the authority detector handles god claims).
    """

    def __init__(self, titles):
        self.keys = {}
        for r in set(titles):
            k = [w for w in re.findall(r"[a-z]+", r.lower()) if w not in _STOP and len(w) >= 3][:2]
            if k and k != ["god"]:
                self.keys[r] = k
        self.order = sorted(self.keys, key=lambda r: (-len(self.keys[r]), r))   # fixed order: same result every run

    def find(self, text: str) -> Optional[str]:
        words = set(re.findall(r"[a-z]+", text.lower()))
        return next((r for r in self.order if all(w in words for w in self.keys[r])), None)


def role_statements(log: EventLog, folder: str) -> List[tuple]:
    """(ts, agent, stated_role, source) from memories and session goals, after role-play starts."""
    roles = assigned_roles(log)
    m = _RoleMatcher(roles.values())
    names = _names(folder)
    t0 = _role_start(log) or 0
    out = []
    for r in _rows(folder, "agent_memories"):
        t = _ts(r.get("created_at"))
        if t is None or t < t0:
            continue
        for mm in _GOAL.finditer((r.get("content") or "")[:4000]):
            role = m.find(mm.group(1))
            if role:
                out.append((t, names.get(r.get("agent_id")), role, "memory"))
                break
    for r in _rows(folder, "computer_use_sessions"):
        t = _ts(r.get("created_at"))
        if t is None or t < t0:
            continue
        role = m.find((r.get("session_goal") or "").split(":")[0][:40])
        if role:
            out.append((t, names.get(r.get("agent_id")), role, "session"))
    out.sort(key=lambda x: x[0])
    return out


def role_drift(log: EventLog, folder: str, window: int = 30, min_agents: int = 3,
               bucket_minutes: int = 30) -> dict:
    """Compare stated roles with assigned roles; online alert on a burst of mismatches."""
    roles = assigned_roles(log)
    if not roles:
        return {}
    st = [s for s in role_statements(log, folder) if s[1] in roles]
    if not st:
        return {}
    W = window * 60
    alert = None
    recent: List[tuple] = []
    first_mismatch: Dict[str, tuple] = {}
    for t, a, role, src in st:
        if role == roles[a]:
            continue
        first_mismatch.setdefault(a, (t, role, src))
        recent = [x for x in recent if x[0] > t - W] + [(t, a)]
        if alert is None and len({x[1] for x in recent}) >= min_agents:
            alert = t
    B = bucket_minutes * 60
    buckets: Dict[int, List[int]] = defaultdict(lambda: [0, 0])
    for t, a, role, _ in st:
        b = buckets[int(t // B)]
        b[0] += 1
        b[1] += role != roles[a]
    series = [(k * B + B / 2, v[0], v[1]) for k, v in sorted(buckets.items())]
    out = dict(statements=len(st), agents_with_statements=len({s[1] for s in st}),
               mismatching=sum(1 for s in st if s[2] != roles[s[1]]),
               agents_drifted=len(first_mismatch), alert=alert,
               params=dict(window=window, min_agents=min_agents),
               first_mismatch=sorted(((a, t, r, src) for a, (t, r, src) in first_mismatch.items()),
                                     key=lambda x: x[1]),
               series=series)
    if alert:
        before = [s for s in st if s[0] < alert - W]
        out["before_alert"] = dict(statements=len(before),
                                   mismatching=sum(1 for s in before if s[2] != roles[s[1]]))
    ms = sorted((getattr(log, "milestones", {}) or {}).items(), key=lambda x: x[1])
    if alert and ms:
        prev = [(k, v) for k, v in ms if v <= alert]
        nxt = [(k, v) for k, v in ms if v > alert]
        if prev:
            out["after_milestone"] = dict(milestone=prev[-1][0], delay_minutes=round((alert - prev[-1][1]) / 60, 1))
        if nxt:
            out["before_next_milestone_hours"] = round((nxt[0][1] - alert) / 3600, 2)
    return out


def rule_breaks(log: EventLog, folder: str, privileged: Optional[set] = None) -> dict:
    """Code commits and direct world-state commits after role-play starts, by agent."""
    names = _names(folder)
    sess = {r["id"]: names.get(r.get("agent_id")) for r in _rows(folder, "computer_use_sessions")}
    t0 = _role_start(log) or 0
    code: Dict[str, List[dict]] = defaultdict(list)
    state: Dict[str, List[dict]] = defaultdict(list)
    interface = Counter()
    other_commits = Counter()
    commands = 0
    for r in _rows(folder, "computer_use_turns"):
        cmd = (r.get("agent_action") or {}).get("command")
        if not cmd:
            continue
        commands += 1
        t = _ts(r.get("created_at"))
        if t is None or t < t0:
            continue
        a = sess.get(r.get("session_id"))
        if _INTERFACE.search(cmd):
            interface[a] += 1
        if not _COMMIT.search(cmd):
            continue
        adds = " ".join(_ADD.findall(cmd))
        py = sorted({p for p in re.findall(r"[\w./-]+\.py\b", adds) if not p.startswith("/tmp")})
        world = bool(re.search(r"\bworld\.json\b", adds))
        landed = bool(_LANDED.search(str(r.get("output") or "")))
        if py:
            code[a].append(dict(ts=t, files=py[:4], landed=landed))
        if world:
            state[a].append(dict(ts=t, landed=landed))
        if not py and not world:
            other_commits[a] += 1
    privileged = privileged or set()

    def rows(d):
        out = []
        for a, v in d.items():
            out.append(dict(agent=a, privileged=a in privileged, attempts=len(v),
                            landed=sum(1 for x in v if x["landed"]),
                            first=min(x["ts"] for x in v),
                            files=sorted({f for x in v for f in x.get("files", [])})[:6]))
        return sorted(out, key=lambda r: (-r["landed"], -r["attempts"]))

    return dict(commands=commands,
                interface_agents=len(interface), interface_uses=sum(interface.values()),
                other_commits=sum(other_commits.values()),
                code=rows(code), world_state=rows(state),
                code_landed_unprivileged=sorted({r["agent"] for r in rows(code)
                                                 if r["landed"] and not r["privileged"]}))


def run_all(log: EventLog, authority: Optional[dict] = None) -> dict:
    folder = getattr(log, "folder", None)
    if not (_has(folder, "agent_memories") or _has(folder, "computer_use_turns")):
        return {}
    out = {}
    if _has(folder, "agent_memories") or _has(folder, "computer_use_sessions"):
        out["role_drift"] = role_drift(log, folder)
    if _has(folder, "computer_use_turns"):
        # "Privileged" = assigned god at any time, so claimants who were not
        # assigned still count as unprivileged.
        from .authority import assigned_holder
        priv = set()
        for role in (authority or {"god": None}):
            priv |= set(assigned_holder(log, role, (_role_start(log) or 0) + 1))
        out["rule_breaks"] = rule_breaks(log, folder, priv)
        claim = {c["agent"] for r in (authority or {}).values() for c in r.get("claimants", [])
                 if not c["assigned"]}
        out["rule_breaks"]["unassigned_claimants"] = sorted(claim)
    return out
