"""Unit tests for the detectors used on attributed logs (AI Village style).

Each test builds a tiny log where the right answer is known by construction.
Run: python tests/test_detectors.py   (or pytest)
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swarmscope.events import Event, EventLog                         # noqa: E402
from swarmscope.detectors import (changepoint, conversation, diffusion, authority,  # noqa: E402
                                  rooms, emergence, influence, early_warning)

T0 = 1788084000.0   # 2026-08-30 10:00 UTC


def chat(i, actor, text, ts, recipients=(), room="room:a", refs=None):
    return Event(event_id=f"e{i}", source="test", seq=i, kind="chat", actor=actor, actor_conf=1.0,
                 recipients=list(recipients), channel=room, refs=refs or {}, ts=ts, ts_source="native",
                 meta={"text_lc": text.lower()})


# ---------------------------------------------------------------- conversation
def test_gini_and_reciprocity():
    assert conversation.gini([3, 3, 3, 3]) == 0.0
    assert conversation.gini([9, 1, 1, 1]) == 0.5           # docstring example
    ev = [chat(0, "a", "@b hi", T0, ["b"]), chat(1, "b", "@a hi", T0 + 60, ["a"]),
          chat(2, "c", "@a hello", T0 + 120, ["a"])]
    st = conversation.network_stats(EventLog(ev))
    assert st["addressed_pairs"] == 3 and abs(st["reciprocity"] - 2 / 3) < 1e-3
    lat = conversation.reply_latency(EventLog(ev))
    assert lat["answered"] == 1 and lat["median_minutes"] == 1.0   # b answered a after 1 minute


# ---------------------------------------------------------------- diffusion
def test_cascade_prefers_addressing_source():
    # docstring example: A uses X at 10:00, B at 10:05, C at 10:30; A addressed C at 10:20 -> C's source is A
    uses = [(T0, "A", "1"), (T0 + 300, "B", "2"), (T0 + 1800, "C", "3")]
    addr = {("A", "C"): [T0 + 1200]}
    c = diffusion.cascade(uses, addr)
    assert dict((ch, p) for p, ch in c["tree"]) == {"B": "A", "C": "A"}
    assert c["depth"] == 1 and c["reach"] == 3 and c["sourced_by_address"] == 0.5


def test_rate_change_counts_windows():
    ev = [chat(i, f"a{i}", "my new role is mayor" if i in (12, 13) else "hello", T0 + i * 60) for i in range(20)]
    r = diffusion.rate_change(EventLog(ev), r"new role", (T0, T0 + 600), (T0 + 600, T0 + 1200))
    assert r["before"]["matching"] == 0 and r["after"]["matching"] == 2


# ---------------------------------------------------------------- changepoint
def test_changepoint_flags_topic_shift_and_scores_it():
    random.seed(0)
    ev, i = [], 0
    for m in range(0, 16 * 60):               # 16 hours, one message a minute (the topic test needs 20 per window)
        words = "build code engine test merge" if m < 10 * 60 else "role mayor court election vote"
        ev.append(chat(i, f"a{i % 9}", " ".join(random.sample(words.split(), 3)), T0 + m * 60)); i += 1
    log = EventLog(ev)
    log.milestones = {"start": T0, "shift": T0 + 10 * 3600}
    d = changepoint.run_all(log)
    assert d["alerts"], "a full change of vocabulary must alert"
    assert d["score"]["detected"] == 1 and d["score"]["milestones"][0]["delay_minutes"] <= 60


def test_changepoint_skips_empty_windows():
    # two busy days with a night gap: the gap must not create alerts by itself
    ev, i = [], 0
    for day in range(2):
        for m in range(0, 8 * 60, 2):
            ev.append(chat(i, f"a{i % 5}", "build code engine", T0 + day * 86400 + m * 60)); i += 1
    d = changepoint.detect(EventLog(ev))
    assert all(s["n"] > 0 for s in d["series"])


# ---------------------------------------------------------------- authority
def test_authority_claims_and_petitions():
    log = EventLog([
        chat(0, "x", "x claims god (emergency protocol)", T0 + 600),
        chat(1, "y", "god desk petition @x (y)", T0 + 700, ["x"]),          # petition, not a claim
        chat(2, "z", "filed revive (file as agent=god)", T0 + 800),          # field value, not a claim
        chat(3, "g", "i am god #1", T0 + 300),
        chat(4, "w", "@x god please revive me", T0 + 900, ["x"]),
    ])
    log.agent_goals = {"g": [(T0, "god — edits code")], "x": [(T0, "Mayor")], "y": [(T0, "Baker")],
                       "z": [(T0, "Clerk")], "w": [(T0, "Smith")]}
    who = sorted(c["agent"] for c in authority.claims(log, "god", since=T0))
    assert who == ["g", "x"], who
    r = authority.run_all(log)["god"]
    x = next(c for c in r["claimants"] if c["agent"] == "x")
    assert not x["assigned"] and x["endorsers"] == 2 and r["unassigned_claimants"] == 1


# ---------------------------------------------------------------- private-channel limit
def test_private_group_limit_scales():
    assert early_warning.private_group_limit(6) == 0      # game-jam: signal off
    assert early_warning.private_group_limit(25) == 2
    assert early_warning.private_group_limit(133) == 3


# ---------------------------------------------------------------- rooms
def test_rooms_private_and_leak():
    ev, i = [], 0
    for k in range(30):
        ev.append(chat(i, f"a{k % 30}", "hello all", T0 + i * 60, room="room:main")); i += 1
    for k in range(8):                        # a 2-agent side room coins "secret-plan"
        ev.append(chat(i, ["p", "q"][k % 2], "the secret-plan is ready", T0 + i * 60, room="room:side")); i += 1
    for k in range(4):                        # 4 agents later use it in the main room
        ev.append(chat(i, f"a{k}", "about the secret-plan", T0 + i * 60, room="room:main")); i += 1
    log = EventLog(ev)
    log.roster_size = 32
    r = rooms.run_all(log)
    side = next(x for x in r["table"] if x["room"] == "room:side")
    assert side["private"] and r["private_rooms"] == ["room:side"]
    assert side["leaked_items"] >= 1 and side["leak_examples"][0][0] == "secret-plan"


# ---------------------------------------------------------------- emergence
def test_pid_known_cases():
    random.seed(1)
    a = [random.randint(0, 1) for _ in range(4000)]
    b = [random.randint(0, 1) for _ in range(4000)]
    assert emergence.pid_synergy(a, b, [x ^ y for x, y in zip(a, b)], kt=2) > 0.9   # XOR: pure synergy
    assert emergence.pid_synergy(a, b, a, kt=2) < 0.05                               # copy: no synergy
    assert abs(emergence.mi(a, a) - 1.0) < 0.01


def test_emergence_runs_and_reports_null():
    ev, i = [], 0
    random.seed(2)
    for b in range(250):                      # 250 ten-minute bins (under 48 h), 12 agents posting at random
        for a in range(12):
            if random.random() < 0.4:
                ev.append(chat(i, f"ag{a}", "x", T0 + b * 600 + a)); i += 1
    r = emergence.run_all(EventLog(ev), B=50, n_random=2)
    tg = r["top_group"]
    assert r["null"].startswith("circular shifts") and 0 <= tg["synergy_p"] <= 1
    assert tg["synergy_p"] > 0.01, "independent agents should not look synergistic"


# ---------------------------------------------------------------- influence
def test_influence_uptake_beats_before_window():
    ev, i = [], 0
    for k in range(30):
        t = T0 + k * 3600
        ev.append(chat(i, f"a{k % 4}", "routine status update", t - 300)); i += 1           # before: unrelated
        ev.append(chat(i, f"human:{k:08d}", f"please check zebrafish{k} quokka{k} now", t)); i += 1
        if k % 2 == 0:                                                                   # half are taken up
            ev.append(chat(i, f"a{k % 4}", f"looking at zebrafish{k} and quokka{k}", t + 120)); i += 1
        for j in range(3):
            ev.append(chat(i, f"a{j}", "more routine work", t + 900 + j)); i += 1
    r = influence.run_all(EventLog(ev))
    assert r["all_human"]["rate_after"] == 0.5 and r["all_human"]["rate_before"] == 0.0
    assert r["instructions"]["count"] == 30


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok ", name)
