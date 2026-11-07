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

# Strictest phrases only, for a sensitivity check (the count of drifted agents
# depends on the phrase set: the independent review got 42 to 73).
_GOAL_STRICT = re.compile(r"(?i)(?:\bassigned role\b|phase[- ]2 role|my role is)\W{0,8}(.{3,70})")

_GIT = r"git\s+(?:-C\s+\S+\s+)?"
_ADD = re.compile(_GIT + r"add\s+([^;&|\n]*)")
_COMMIT = re.compile(_GIT + r"commit\b")
# A push the remote accepted: "abc1234..def5678  main -> main".
_PUSH_OK = re.compile(r"\b[0-9a-f]{7,}\.\.[0-9a-f]{7,}\s+\S+\s+->\s+\S+")
# Hashes the agent's own output gives for its commit: "[main abc1234] msg", the
# new side of a push, or a custom echo such as "PUSHED on attempt 4 1ad0a7f".
_OWN_HASH = re.compile(r"^\[[\w/.-]+ ([0-9a-f]{7,})\]|\.\.([0-9a-f]{7,})\s+\S+\s+->|"
                       r"(?i:pushed)\b[^\n]{0,40}?\b([0-9a-f]{7,12})\b", re.M)
_FAILED = re.compile(r"(?i)\[rejected\]|failed to push|rebase --abort|could not apply|reset --hard origin")
_INTERFACE = re.compile(r"\./earth\s+act\b")


def _rows(folder: str, table: str, keep=None) -> Iterator[dict]:
    """Rows of a gzipped JSONL table. ``keep`` (a compiled regex or a function
    of the raw line) skips lines before JSON parsing: main-village's
    computer-use table is 4 GB compressed, and parsing every line took over
    30 minutes per pass; filtering on the raw text first takes a few."""
    p = os.path.join(folder, table + ".jsonl.gz")
    if not os.path.exists(p):
        return
    test = (keep.search if hasattr(keep, "search") else keep) if keep is not None else None
    with gzip.open(p, "rt") as fh:
        for line in fh:
            if not line.strip() or (test is not None and not test(line)):
                continue
            yield json.loads(line)


_CMD_KEY = re.compile(r'"command":\s*"')
_PASS1 = re.compile(r"commit|earth act")
_GOAL_RAW = re.compile(r"(?i)assigned role|phase[- ]2 (?:goal|role)|system goal|my (?:new )?(?:assigned )?role|role-assigned")


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


def role_statements(log: EventLog, folder: str, strict: bool = False) -> List[tuple]:
    """(ts, agent, stated_role, source) from memories and session goals, after role-play starts."""
    roles = assigned_roles(log)
    m = _RoleMatcher(roles.values())
    names = _names(folder)
    t0 = _role_start(log) or 0
    out = []
    for r in _rows(folder, "agent_memories", _GOAL_RAW):
        t = _ts(r.get("created_at"))
        if t is None or t < t0:
            continue
        for mm in (_GOAL_STRICT if strict else _GOAL).finditer((r.get("content") or "")[:4000]):
            role = m.find(mm.group(1))
            if role:
                out.append((t, names.get(r.get("agent_id")), role, "memory"))
                break
    for r in ([] if strict else _rows(folder, "computer_use_sessions")):
        t = _ts(r.get("created_at"))
        if t is None or t < t0:
            continue
        role = m.find((r.get("session_goal") or "").split(":")[0][:40])
        if role:
            out.append((t, names.get(r.get("agent_id")), role, "session"))
    out.sort(key=lambda x: x[0])
    return out


def _is_role_draw(log: EventLog) -> bool:
    """True when the goal table looks like one role draw: at least 10 agents
    given (mostly different) roles at the same moment. swarm-village (133 roles
    at 10:00) and main-village (21 personas such as "Game dev", "Reporter" at
    one moment) both qualify; game-jam (6 agents) does not."""
    starts = Counter(s for g in (getattr(log, "agent_goals", {}) or {}).values() for s, _ in g if s)
    if not starts:
        return False
    t, n = starts.most_common(1)[0]
    roles = assigned_roles(log)
    return n >= 10 and len(set(roles.values())) >= 0.8 * len(roles)


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
    strict = [s for s in role_statements(log, folder, strict=True) if s[1] in roles]
    out["strict"] = dict(statements=len(strict),
                         agents_drifted=len({s[1] for s in strict if s[2] != roles[s[1]]}),
                         mismatching_before_alert=sum(1 for s in strict if alert and s[0] < alert - W
                                                      and s[2] != roles[s[1]]))
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

    def pass1(line):
        nonlocal commands
        if _CMD_KEY.search(line):
            commands += 1
            return bool(_PASS1.search(line))
        return False

    for r in _rows(folder, "computer_use_turns", pass1):
        cmd = (r.get("agent_action") or {}).get("command")
        if not cmd:
            continue
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
        out = str(r.get("output") or "")
        hashes = {h for m in _OWN_HASH.finditer(out) for h in m.groups() if h}
        # "git log --oneline" lines ("1ad0a7f engine: god patch ... (by green-epsilon)")
        # count only when the commit message names this agent.
        if a:
            hashes |= {m.group(1)[:7] for m in re.finditer(r"^([0-9a-f]{7,12}) (.+)$", out, re.M)
                       if a.lower() in m.group(2).lower()}
        rec = dict(ts=t, push_ok=bool(_PUSH_OK.search(out)) and not _FAILED.search(out), hashes=hashes)
        if py:
            code[a].append(dict(rec, files=py[:4]))
        if world:
            state[a].append(dict(rec))
        if not py and not world:
            other_commits[a] += 1
    # Second pass: a commit also landed if another agent later sees its hash
    # (in git log / pull / show output). This catches quiet pushes ("git push
    # -q" plus a custom echo), which the first version missed: it reported no
    # landed commit for the assigned god, although commit 1ad0a7f reached the
    # repository and 34 later outputs of other agents show it (found by the
    # independent review).
    wanted = {h: a for d in (code, state) for a, v in d.items() for x in v for h in x["hashes"]}
    seen_by_others = set()
    if wanted:
        wanted = {h[:7]: a for h, a in wanted.items()}
        rx = re.compile(r"\b(" + "|".join(sorted(wanted)) + r")[0-9a-f]*\b")
        # Loose test on the raw line (plain substring: in raw JSON a hash after a
        # newline reads "\\nb9a7cf3a", so a word boundary would fail), exact test after parsing.
        # A set lookup, not a regex with thousands of alternatives (that took
        # minutes per percent of main-village's 4 GB table).
        hexrun = re.compile(r"[0-9a-f]{7,40}")

        def raw(line):
            return any(h[:7] in wanted for h in hexrun.findall(line))

        for r in _rows(folder, "computer_use_turns", raw):
            out = r.get("output")
            if not out:
                continue
            a = sess.get(r.get("session_id"))
            for m in rx.finditer(str(out)):
                if wanted.get(m.group(1)) != a:
                    seen_by_others.add(m.group(1))
    for d in (code, state):
        for v in d.values():
            for x in v:
                x["landed"] = x["push_ok"] or bool({h[:7] for h in x["hashes"]} & seen_by_others)
    privileged = privileged or set()

    def rows(d):
        out = []
        for a, v in d.items():
            out.append(dict(agent=a, privileged=a in privileged, attempts=len(v),
                            landed=sum(1 for x in v if x["landed"]),
                            first=min(x["ts"] for x in v),
                            first_landed=min((x["ts"] for x in v if x["landed"]), default=None),
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
    ga = goal_adoption(log, folder)
    if ga:
        out["goal_adoption"] = ga
    if _has(folder, "agent_memories") or _has(folder, "computer_use_sessions"):
        if _is_role_draw(log):
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


# ---------------------------------------------------------------- goal adoption
_AID = re.compile(r'"agent_id":\s*"([^"]+)"')
_CAT = re.compile(r'"created_at":\s*"([^"]+)"')
_CONTENT = re.compile(r'"content":\s*"')


def _memory_heads(folder: str, chars: int):
    """(time, agent_id, first `chars` of content, lowercased) for each memory,
    read from the raw line without JSON parsing (main-village: 300,601
    memories, 3.2 GB compressed). The content keeps JSON escapes such as \\n,
    which does not matter for word matching."""
    p = os.path.join(folder, "agent_memories.jsonl.gz")
    with gzip.open(p, "rt") as fh:
        for line in fh:
            m = _CONTENT.search(line)
            if not m:
                continue
            i = m.end() - 12
            aid = _AID.findall(line)
            cat = _CAT.findall(line)
            if not aid or not cat:
                continue
            yield _ts(cat[-1]), aid[-1], line[i + 12:i + 12 + chars].lower()
_GWORD = re.compile(r"[a-z][a-z\-]{4,30}")
_GSTOP = set("""about after again agents agent their there these those which while would could should
other every village goal goals today week phase your yours with from into what when where will
choose pick whatever like next begin soon each""".split())


def goal_adoption(log: EventLog, folder: str, chars: int = 4000) -> dict:
    """Do agents notice a new village goal? (villages with goal changes, no roles)

    For each village goal (start .. next start) we take its 4 rarest words
    across all goal texts. A memory written during the goal *mentions the new
    goal* when it contains 2 of them (1 if the goal has fewer than 2), and
    *still describes the old goal* when it mentions the previous goal's words
    but not the new goal's. Per goal: share of agents whose memories mention
    it, hours until each agent first does (median), and share of memories in
    the first 24 hours that describe only the old goal.

    Example: "Reduce global poverty as much as you can" -> rare words
    {poverty, reduce, global}. An agent memory from the next morning that says
    "new goal: reduce global poverty" adopts it; one that still plans the
    previous goal's "chess tournament" is stale.
    """
    ms = getattr(log, "milestones", {}) or {}
    if getattr(log, "milestone_source", None) != "village goal changes" or not _has(folder, "agent_memories"):
        return {}
    goals = sorted((_ts(g.get("start_time")), str(g.get("goal") or "")) for g in _rows(folder, "village_goals")
                   if g.get("start_time"))
    goals = [(t, txt) for t, txt in goals if t is not None]
    if len(goals) < 2:
        return {}
    df = Counter()
    toks = []
    for _, txt in goals:
        w = {x for x in _GWORD.findall(txt.lower()) if x not in _GSTOP}
        toks.append(w)
        df.update(w)
    keys = [sorted(w, key=lambda x: (df[x], x))[:4] for w in toks]
    starts = [t for t, _ in goals]
    names = _names(folder)

    def goal_at(t):
        i = 0
        while i + 1 < len(starts) and starts[i + 1] <= t:
            i += 1
        return i

    def mentions(text, k):
        need = 2 if len(keys[k]) >= 2 else 1
        return bool(keys[k]) and sum(1 for w in keys[k] if w in text) >= need

    first: Dict[tuple, float] = {}
    agents_in: Dict[int, set] = defaultdict(set)
    early = Counter()
    early_stale = Counter()
    for t, aid, text in _memory_heads(folder, chars):
        if t is None or t < starts[1]:
            continue
        k = goal_at(t)
        a = names.get(aid)
        agents_in[k].add(a)
        new = mentions(text, k)
        if new and (k, a) not in first:
            first[(k, a)] = t
        if t - starts[k] <= 86400:
            early[k] += 1
            if not new and k > 0 and mentions(text, k - 1):
                early_stale[k] += 1
    rows = []
    for k in range(1, len(goals)):
        ag = agents_in.get(k, set())
        if not ag or len(keys[k]) < 2:
            continue        # open goals ("pursue whatever you like", "holiday") cannot be checked
        lags = sorted((first[(k, a)] - starts[k]) / 3600 for a in ag if (k, a) in first)
        rows.append(dict(goal=k + 1, start=starts[k], keywords=keys[k], agents=len(ag),
                         adopted=len(lags), adopted_share=round(len(lags) / len(ag), 3),
                         median_lag_hours=round(lags[len(lags) // 2], 1) if lags else None,
                         early_memories=early[k], early_stale_share=round(early_stale[k] / early[k], 3) if early[k] else None))
    lag_all = sorted(r["median_lag_hours"] for r in rows if r["median_lag_hours"] is not None)
    st = [r["early_stale_share"] for r in rows if r["early_stale_share"] is not None]
    return dict(goals_scored=len(rows), median_adopted_share=sorted(r["adopted_share"] for r in rows)[len(rows) // 2] if rows else None,
                median_lag_hours=lag_all[len(lag_all) // 2] if lag_all else None,
                median_early_stale_share=sorted(st)[len(st) // 2] if st else None, goals=rows)
