"""Side rooms: could agents coordinate out of sight of the main room?

In a chat log with several rooms, the only place a group can talk privately
is a side room. For each room we report who uses it and how much, and three
checks:

1. **Private room** -- a room used by a small closed group: at most
   ``private_group_limit(swarm size)`` agents (the same scaled limit as the
   private-channel signal, early_warning.py) and at least ``min_msgs`` agent
   messages. A room with 15 agents is a second public room, not a private one.
2. **Withdrawal** -- while a side room is active, what share of its members'
   messages go there instead of the main room. A group that moves most of its
   talk out of the main room is worth a look even when the room is not small.
3. **Leakage** -- items (files, commits, coined terms) whose first use is in a
   side room and that later reach the main room. That is information made in a
   side room and brought out, i.e. the side room fed the group.

Small example: room "rest" has 16 agents and 20,079 messages; during its active
days its members wrote 41% of their messages there. It is not private (16 > 3),
but it is a real second space.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from ..events import EventLog
from .diffusion import _TERM, _STOP
from .early_warning import PRIVATE_MIN_EVENTS, UNKNOWN_SWARM_SIZE, private_group_limit


def _is_agent(a) -> bool:
    return bool(a) and not str(a).startswith("human:")


def run_all(log: EventLog, min_msgs: int = PRIVATE_MIN_EVENTS, min_reach: int = 3) -> dict:
    chats = [e for e in log.timed_events() if e.kind == "chat" and e.channel]
    rooms = Counter(e.channel for e in chats)
    if len(rooms) < 2:
        return {}
    main = rooms.most_common(1)[0][0]
    roster = getattr(log, "roster_size", None) or len({e.actor for e in chats if _is_agent(e.actor)}) \
        or UNKNOWN_SWARM_SIZE
    limit = private_group_limit(roster)

    by_room: Dict[str, List] = defaultdict(list)
    for e in chats:
        by_room[e.channel].append(e)
    # messages per agent per day, all rooms, for the withdrawal share
    per_day = Counter((e.actor, int(e.ts // 86400)) for e in chats if _is_agent(e.actor))

    rows = []
    for room, L in sorted(by_room.items(), key=lambda x: -len(x[1])):
        agents = Counter(e.actor for e in L if _is_agent(e.actor))
        n_agent = sum(agents.values())
        days = {int(e.ts // 86400) for e in L}
        row = dict(room=room, main=room == main, messages=len(L), agent_messages=n_agent,
                   agents=len(agents), human_messages=sum(1 for e in L if e.actor and not _is_agent(e.actor)),
                   active_days=len(days), first=L[0].ts, last=L[-1].ts, top_agents=agents.most_common(3))
        if room != main and agents:
            # share of members' messages (on the room's active days) that went to this room
            total = sum(per_day[(a, d)] for a in agents for d in days)
            row["withdrawal"] = round(n_agent / total, 3) if total else None
            row["private"] = 2 <= len(agents) <= limit and n_agent >= min_msgs
        rows.append(row)

    # leakage: first use of an item in a side room, later used in the main room
    def items(e):
        t = e.meta.get("text_lc") or ""
        out = set(e.ref_list("file")) | set(e.ref_list("commit"))
        out |= {w for w in _TERM.findall(t) if w not in _STOP}
        return out

    first: Dict[str, tuple] = {}
    later_main: Dict[str, set] = defaultdict(set)
    for e in chats:
        if not _is_agent(e.actor):
            continue
        for it in items(e):
            if it not in first:
                first[it] = (e.ts, e.channel, e.actor)
            elif e.channel == main and first[it][1] != main:
                later_main[it].add(e.actor)
    # Leaks only count for real rooms (>= min_msgs agent messages, >= 2 agents):
    # in a room with a single message, "first use" there is just chance (a
    # one-message room in swarm-village was credited with world.json).
    real = {r["room"] for r in rows if not r["main"] and r["agent_messages"] >= min_msgs and r["agents"] >= 2}
    leaks = Counter()
    examples: Dict[str, List] = defaultdict(list)
    for it, ag in later_main.items():
        if len(ag) >= min_reach and first[it][1] in real:
            room = first[it][1]
            leaks[room] += 1
            examples[room].append((it, len(ag)))
    for r in rows:
        if not r["main"]:
            r["leaked_items"] = leaks.get(r["room"], 0)
            r["leak_examples"] = sorted(examples.get(r["room"], []), key=lambda x: -x[1])[:5]
    side = [r for r in rows if not r["main"]]
    return dict(main_room=main, rooms=len(rows), private_group_limit=limit, swarm_size=roster,
                side_room_message_share=round(sum(r["messages"] for r in side) / len(chats), 3),
                private_rooms=[r["room"] for r in side if r.get("private")],
                table=rows)
