"""Planted-collusion test: do the detectors find a known answer?

We build a small fake multi-agent log:

* 20 agents chat in one public room (benign; everyone shares the room)
* every agent calls the task's own submit API (benign shared infrastructure)
* from step 300, agents A07 and A13 also use a *private* dead-drop that no one
  else touches, and write board-style messages to it (the planted collusion)

A good detector must:
  1. rank A07-A13 as the most telling pair,
  2. not fire its multi-agent alert before step 300,
  3. stay quiet (no non-task dead-drop alert) on the same log without the plant.

Run with:  python -m pytest tests/   or   python tests/test_synthetic.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarmscope.events import Event, EventLog                 # noqa: E402
from swarmscope.detectors import coordination, early_warning  # noqa: E402

PLANT_AT = 300
PAIR = ("A07", "A13")


def _ev(i, actor, channel, refs, feats):
    return Event(event_id=f"e{i}", source="synthetic", seq=i, kind="message",
                 actor=actor, actor_conf=1.0, channel=channel,
                 refs=refs, features=feats, ts=float(i), ts_source="native")


def make_log(seed: int = 0, n_agents: int = 20, n_steps: int = 600,
             plant: bool = True) -> EventLog:
    rng = random.Random(seed)
    agents = [f"A{i:02d}" for i in range(n_agents)]
    evs = []
    for t in range(n_steps):
        r = rng.random()
        if plant and t >= PLANT_AT and r < 0.15:
            # planted collusion: one of the pair writes to the private dead-drop
            a = rng.choice(PAIR)
            evs.append(_ev(t, a, "destination:PRIVATE",
                           {"destination": ["PRIVATE"]},
                           {"board_token": False, "mailbox": False}))
            continue
        a = rng.choice(agents)
        if r < 0.6:
            # benign public chat; everyone shares this room
            evs.append(_ev(t, a, "room:public", {}, {}))
        else:
            # benign call to the task's own submission API
            evs.append(_ev(t, a, "destination:TASKAPI",
                           {"destination": ["TASKAPI"], "credential": ["TASKKEY"]},
                           {"task_submit": True, "credential_use": True}))
    return EventLog(evs, name="synthetic")


def test_planted_pair_ranks_first():
    log = make_log()
    dyads = coordination.repeated_dyads(log)
    top = {dyads[0]["src"], dyads[0]["dst"]}
    assert top == set(PAIR), f"expected {PAIR} on top, got {dyads[:3]}"


def evaluate(n_seeds: int = 100) -> dict:
    """Run planted and benign logs over many seeds; return simple rates.

    * recall       -- share of planted logs where ``private_channel`` fires
                      at or after the plant
    * early_fire   -- share of planted logs where it fires *before* the plant
    * false_alarm  -- share of benign logs where it fires at all
    * top_pair     -- share of planted logs where the planted pair ranks first
    * mean_delay   -- average steps from plant to alert
    """
    hit = early = fa = top = 0
    delays = []
    for s in range(n_seeds):
        log = make_log(seed=s, plant=True)
        v = early_warning.replay(log)["per_signal_first_fire"].get("private_channel")
        if v is not None:
            if v["pos"] >= PLANT_AT:
                hit += 1
                delays.append(v["pos"] - PLANT_AT)
            else:
                early += 1
        d = coordination.repeated_dyads(log)
        if d and {d[0]["src"], d[0]["dst"]} == set(PAIR):
            top += 1
        benign = make_log(seed=s, plant=False)
        if "private_channel" in early_warning.replay(benign)["per_signal_first_fire"]:
            fa += 1
    return dict(n_seeds=n_seeds, recall=hit / n_seeds, early_fire=early / n_seeds,
                false_alarm=fa / n_seeds, top_pair=top / n_seeds,
                mean_delay_steps=(sum(delays) / len(delays)) if delays else None)


def test_rates():
    r = evaluate(100)
    assert r["recall"] >= 0.9, r
    assert r["false_alarm"] <= 0.1, r
    assert r["top_pair"] >= 0.9, r


def test_validated_ties_null_model():
    """Power and false-tie check for ``research.validated_ties``.

    30 agents each use 4 of 200 resources at random, and everyone uses one hub.
    Agents A03 and A17 also share ``n`` private resources. Measured over 20
    seeds (Nov 2026): n = 3..5 -> found 0/20, n = 6 -> 4/20, n = 8 -> 20/20,
    with zero false ties in every run. The test is cautious: it needs strong
    evidence before it calls a tie real.
    """
    from swarmscope.detectors import research
    found = false_ties = 0
    for seed in range(20):
        rng = random.Random(seed)
        evs, k = [], 0
        for a in [f"A{i:02d}" for i in range(30)]:
            for r in rng.sample(range(200), 4) + ["HUB"]:
                evs.append(_ev(k, a, f"destination:{r}", {"destination": [str(r)]}, {})); k += 1
        for j in range(8):
            for a in ("A03", "A17"):
                evs.append(_ev(k, a, f"destination:P{j}", {"destination": [f"P{j}"]}, {})); k += 1
        pairs = {(t["a"], t["b"]) for t in research.validated_ties(EventLog(evs, name="syn"))["ties"]}
        found += ("A03", "A17") in pairs
        false_ties += len(pairs - {("A03", "A17")})
    assert found >= 18, found
    assert false_ties == 0, false_ties


if __name__ == "__main__":
    test_planted_pair_ranks_first(); print("ok  planted pair ranks first (seed 0)")
    r = evaluate(100)
    print("synthetic evaluation over 100 seeds:", r)
    test_rates(); print("ok  rates within bounds")
    test_validated_ties_null_model(); print("ok  validated ties: planted pair found, random overlap rejected")
