"""Smoke tests: each loader runs end to end on a tiny fake file.

These check that a data source flows through load -> analyze -> write_outputs
without crashing, plus a few loader facts. The AI Village fixture follows the
real table schema from the dataset's SCHEMA.md (checked Nov 2026): ids for
agents and rooms, naive UTC timestamps, and an events table.

Run with:  python -m pytest tests/   or   python tests/test_loaders.py
"""

import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarmscope.loaders import ai_village, generic  # noqa: E402
from swarmscope import report                       # noqa: E402

ROWS = [
    {"room": "general", "speaker": "Claude", "content": "@Gemini can you check the doc?", "timestamp": "2026-08-29T17:00:00Z"},
    {"room": "general", "speaker": "Gemini", "content": "On it @Claude", "timestamp": "2026-08-29T17:01:00Z"},
    {"room": "general", "speaker": "o3", "content": "I posted the sheet", "timestamp": "2026-08-29T17:02:00Z"},
    {"room": "side", "speaker": "Claude", "content": "quick note for @o3", "timestamp": "2026-08-29T17:03:00Z"},
    {"room": "side", "speaker": "o3", "content": "thanks @Claude", "timestamp": "2026-08-29T17:04:00Z"},
]


def _write_gz(rows, path):
    with gzip.open(path, "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _village_tables(d):
    """Write a tiny village in the real table schema (SCHEMA.md, Nov 2026)."""
    names = {"a1": "Claude Opus 4.5", "a2": "Gemini 2.5 Pro", "a3": "o3"}
    rooms = {"r1": "general", "r2": "side"}
    _write_gz([{"id": k, "name": v, "model_string": v.lower()} for k, v in names.items()],
              os.path.join(d, "agents.jsonl.gz"))
    _write_gz([{"id": k, "name": v} for k, v in rooms.items()], os.path.join(d, "chat_rooms.jsonl.gz"))
    by_name = {v: k for k, v in names.items()}
    msgs = []
    for i, r in enumerate(ROWS):
        speaker = {"Claude": "Claude Opus 4.5", "Gemini": "Gemini 2.5 Pro", "o3": "o3"}[r["speaker"]]
        content = (r["content"].replace("@Gemini", "Gemini 2.5 Pro").replace("@Claude", "Claude Opus 4.5")
                   + (" see https://docs.google.com/document/d/abc123/edit?usp=sharing" if i in (0, 2) else ""))
        msgs.append({"id": f"m{i}", "speaker_type": "agent", "agent_speaker_id": by_name[speaker],
                     "user_speaker_id": None, "content": content,
                     "room_id": "r1" if r["room"] == "general" else "r2",
                     "created_at": r["timestamp"].replace("T", " ").replace("Z", ".000001")})
    _write_gz(msgs, os.path.join(d, "chat_messages.jsonl.gz"))
    _write_gz([{"id": "e1", "event_index": 1, "created_at": "2026-08-29 16:59:00.000000",
                "data": {"actionType": "START_USING_COMPUTER", "agentId": "a3", "sessionGoal": "open the sheet"}},
               {"id": "e2", "event_index": 2, "created_at": "2026-08-29 17:00:00.000000",
                "data": {"actionType": "AGENT_TALK", "speakerId": "a1"}}],     # chat: skipped here
              os.path.join(d, "events.jsonl.gz"))


def test_ai_village_tables_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        _village_tables(d)
        log = ai_village.load(d)
        assert len(log) == 6                                   # 5 chat + 1 computer-use start
        assert log.time_axis() == "time"
        assert set(log.actors()) == {"Claude Opus 4.5", "Gemini 2.5 Pro", "o3"}
        first_chat = next(e for e in log.events if e.kind == "chat")
        # A name without "@" is *named* (talked about), not addressed.
        assert first_chat.recipients == [], first_chat.recipients
        assert first_chat.ref_list("handle") == ["Gemini 2.5 Pro"]
        # "@o3" addresses a known agent; "@Claude" is not a full agent name, so it is ignored.
        side = [e for e in log.events if e.kind == "chat" and e.channel == "room:side"]
        assert side[0].recipients == ["o3"] and side[1].recipients == [], [e.recipients for e in side]
        assert first_chat.channel == "room:general"
        # naive timestamps are read as UTC: 2026-08-29 17:00:00 UTC
        assert int(first_chat.ts) == 1788022800, first_chat.ts
        # the same Google Doc posted by two agents is one shared resource
        assert first_chat.ref_list("link") == ["docs.google.com/document/d/abc123/edit"]
        f = report.analyze(log)
        assert f["summary"]["n_shared_deaddrops"] >= 1
        paths = report.write_outputs(log, f, os.path.join(d, "out"))
        assert os.path.getsize(paths["html"]) > 100_000   # D3 is inlined


def test_generic_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "log.jsonl")
        with open(p, "w") as fh:
            for r in ROWS:
                fh.write(json.dumps({"from": r["speaker"], "thread": r["room"],
                                     "body": r["content"], "time": r["timestamp"]}) + "\n")
        log = generic.load(p, {"actor": "from", "channel": "thread", "text": "body", "ts": "time"})
        assert len(log) == 5 and log.events[0].channel == "general"
        f = report.analyze(log)
        assert f["summary"]["n_named_agents"] == 3


def test_timestamps_with_odd_decimals():
    # Python 3.10 cannot read 4 or 5 decimal places by itself.
    t = ai_village.parse_ts("2026-08-30 10:00:00")
    assert t == 1788084000.0
    assert abs(ai_village.parse_ts("2026-08-30 10:00:00.12345") - (t + 0.12345)) < 1e-6
    assert abs(ai_village.parse_ts("2026-08-30 10:00:00.1234") - (t + 0.1234)) < 1e-6


def test_actions_role_drift_and_rule_breaks():
    from types import SimpleNamespace
    from swarmscope.detectors import actions
    t0 = 1788084000.0                                   # 2026-08-30 10:00 UTC
    import datetime as _d
    iso = lambda t: _d.datetime.fromtimestamp(t, _d.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    with tempfile.TemporaryDirectory() as d:
        agents = [{"id": f"id{i}", "name": n} for i, n in enumerate(["a1", "a2", "a3", "god1"])]
        _write_gz(agents, os.path.join(d, "agents.jsonl.gz"))
        roles = {"a1": "Bridge Engineer", "a2": "Grid Technician", "a3": "Fire Chief", "god1": "god"}
        mem = []
        for i, a in enumerate(["a1", "a2", "a3"]):
            # before: each agent quotes its own role; after: a different one
            mem.append({"agent_id": f"id{i}", "created_at": iso(t0 + 600), "content": f"Assigned role: {roles[a]}"})
            other = "Fire Chief" if a != "a3" else "Bridge Engineer"
            mem.append({"agent_id": f"id{i}", "created_at": iso(t0 + 3600 + 60 * i),
                        "content": f"System goal now reads: Play your assigned role: {other}"})
        _write_gz(mem, os.path.join(d, "agent_memories.jsonl.gz"))
        _write_gz([{"id": "s1", "agent_id": "id0", "created_at": iso(t0 + 60), "session_goal": "Bridge Engineer: fix bridge"},
                   {"id": "s4", "agent_id": "id3", "created_at": iso(t0 + 60), "session_goal": "God: patch"}],
                  os.path.join(d, "computer_use_sessions.jsonl.gz"))
        _write_gz([{"session_id": "s1", "created_at": iso(t0 + 120),
                    "agent_action": {"command": "git add mod/x.py && git commit -m x && git push"},
                    "output": "[main abc1234] x\n 1 file changed"},
                   {"session_id": "s4", "created_at": iso(t0 + 130),
                    "agent_action": {"command": "git add engine.py && git commit -m y"}, "output": "[main def5678] y"},
                   {"session_id": "s1", "created_at": iso(t0 + 140),
                    "agent_action": {"command": "./earth act join --agent a1"}, "output": "ok"}],
                  os.path.join(d, "computer_use_turns.jsonl.gz"))
        log = SimpleNamespace(agent_goals={a: [(t0, r)] for a, r in roles.items()},
                              milestones={"op": t0 + 3500}, folder=d)
        rd = actions.role_drift(log, d)
        assert rd["agents_drifted"] == 3 and rd["before_alert"]["mismatching"] == 0, rd
        assert abs(rd["alert"] - (t0 + 3720)) < 1 and rd["after_milestone"]["milestone"] == "op"
        rb = actions.rule_breaks(log, d, privileged={"god1"})
        assert rb["code_landed_unprivileged"] == ["a1"], rb
        assert rb["interface_uses"] == 1


if __name__ == "__main__":
    test_timestamps_with_odd_decimals(); print("ok  timestamps with 4 or 5 decimals")
    test_ai_village_tables_end_to_end(); print("ok  ai_village loader (real schema) end to end")
    test_generic_end_to_end();         print("ok  generic loader end to end")
    test_actions_role_drift_and_rule_breaks(); print("ok  role drift and rule breaks")
