"""How well does SwarmScope do each part of its mission? Experiments with a known answer.

    python scripts/validate_mission.py          # writes outputs/validation.md and outputs/validation.json

Each experiment plants something with a known truth into a REAL log, runs the
tool's own detector on it, and counts how often the tool gets the truth back.
No payload text is read.

1. Who talked to whom (redacted log). A planted pair of agents that share k rare
   resources is added to Swarm Traces. Is the pair found by the tie test, and
   where does it rank by Adamic-Adar weight?
2. How information spread. Items with a known spreading tree are added to the
   real swarm-village chat (its real agents and real @-addresses). How often
   does the cascade rule name the true source? Baselines: the first adopter
   (Goel et al.'s earliest-parent rule) and the latest earlier adopter.
3. Covert channels. A hidden channel (g agents using one new resource n times)
   is added to benign AI Village logs. Does the private-channel signal fire on
   it, how fast, and how many background alerts compete with it?
4. Hidden-channel flags. Rate of each mechanism flag per 1,000 events in the
   attack log and in the four benign villages (from findings.json).
"""

import copy
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from swarmscope.events import Event, EventLog  # noqa: E402
from swarmscope.loaders import ai_village, swarm_traces  # noqa: E402
from swarmscope.detectors import diffusion, early_warning, research  # noqa: E402
from swarmscope import graph  # noqa: E402

DATA = os.environ.get("SWARMSCOPE_DATA", os.path.join(ROOT, "data"))
OUT = os.path.join(ROOT, "outputs")


def village(name):
    return ai_village.load(os.path.join(DATA, "ai-village", name))


def with_events(log, extra):
    new = EventLog(list(log.events) + extra, name=log.name)
    for k in ("roster_size", "folder", "village"):
        if hasattr(log, k):
            setattr(new, k, getattr(log, k))
    return new


def ev(i, actor, ts, refs=None, channel=None, kind="message"):
    return Event(event_id=f"plant{i}", source="plant", seq=10_000_000 + i, kind=kind, actor=actor,
                 actor_conf=1.0, channel=channel, refs=refs or {}, features={}, ts=ts,
                 ts_source="native", ts_precision="second")


# --------------------------------------------------------------------------
# 1. Who talked to whom: planted pair in Swarm Traces
# --------------------------------------------------------------------------
def exp_ties(st, ks=(2, 4, 8, 16), trials=4, seed=1):
    rng = random.Random(seed)
    dated = [e.ts for e in st.events if e.ts and e.ts_precision == "second"]
    lo, hi = min(dated), max(dated)
    rows = []
    for k in ks:
        found, ranks = 0, []
        for t in range(trials):
            pa, pb = f"PLANTA{k}x{t}", f"PLANTB{k}x{t}"
            extra, i = [], 0
            for r in range(k):
                rid = f"PL{k}x{t}x{r}"
                for who in (pa, pb):
                    extra.append(ev(i, who, rng.uniform(lo, hi), refs={"destination": [rid]},
                                    channel=f"destination:{rid}"))
                    i += 1
            log = with_events(st, extra)
            vt = research.validated_ties(log)
            pair = {pa, pb}
            if any({x["a"], x["b"]} == pair for x in vt.get("ties", [])):
                found += 1
            g, _ = graph.build_agent_projection(log, prefer_time=True)
            ws = sorted(((e.get("weight") or 0), e["src"], e["dst"]) for e in g.edges)[::-1]
            target = {f"agent:{pa}", f"agent:{pb}"}
            for rank, (_, s, d) in enumerate(ws, 1):
                if {s, d} == target:
                    ranks.append(rank)
                    break
        rows.append(dict(shared_rare_resources=k, trials=trials, validated=found,
                         median_rank=statistics.median(ranks) if ranks else None))
        print(f"  ties k={k}: validated {found}/{trials}, ranks {ranks}", file=sys.stderr)
    return rows


# --------------------------------------------------------------------------
# 2. How information spread: known trees in the real swarm-village chat
# --------------------------------------------------------------------------
class Merged(dict):
    def __init__(self, base, extra):
        super().__init__()
        self.base, self.extra = base, extra

    def get(self, k, d=()):
        return tuple(self.base.get(k, ())) + tuple(self.extra.get(k, ()))


def exp_spread(log, shares=(1.0, 0.85, 0.5, 0.0), trials=300, seed=2):
    rng = random.Random(seed)
    addr = diffusion._address_times(log)
    agents = sorted({e.actor for e in log.events if e.actor and not str(e.actor).startswith("human:")})
    ts = sorted(e.ts for e in log.events if e.ts)
    lo, hi = ts[0], ts[-1] - 8 * 3600
    rows = []
    for q in shares:
        hit = Counter(); tot = Counter(); base_first = base_last = base_rand = 0.0; n_all = 0
        for _ in range(trials):
            reach = rng.randint(8, 40)
            order = rng.sample(agents, reach)
            t = rng.uniform(lo, hi)
            uses, truth, extra = [(t, order[0], "x")], {}, {}
            for i, a in enumerate(order[1:], start=1):
                t += rng.expovariate(1 / 600)           # mean 10 minutes between adoptions
                s = rng.choice(order[:i])               # true source: any earlier adopter
                mech = "address" if rng.random() < q else "seen"
                if mech == "address":
                    extra.setdefault((s, a), []).append(t - rng.uniform(5, 120))
                truth[a] = (s, mech)
                uses.append((t, a, "x"))
            c = diffusion.cascade(uses, Merged(addr, extra))
            for p, a in c["tree"]:
                s, mech = truth[a]
                tot[mech] += 1; hit[mech] += (p == s)
            for i, a in enumerate(order[1:], start=1):
                s = truth[a][0]
                base_first += (s == order[0]); base_last += (s == order[i - 1]); base_rand += 1 / i
                n_all += 1
        acc = sum(hit.values()) / sum(tot.values())
        rows.append(dict(share_by_address=q, adoptions=n_all, accuracy=round(acc, 3),
                         accuracy_address=round(hit["address"] / tot["address"], 3) if tot["address"] else None,
                         accuracy_seen=round(hit["seen"] / tot["seen"], 3) if tot["seen"] else None,
                         baseline_first_adopter=round(base_first / n_all, 3),
                         baseline_latest_adopter=round(base_last / n_all, 3),
                         baseline_random=round(base_rand / n_all, 3)))
        print(f"  spread q={q}: {rows[-1]}", file=sys.stderr)
    return rows


# --------------------------------------------------------------------------
# 3. Covert channels: planted hidden channel in benign villages
# --------------------------------------------------------------------------
def _pc_times(log):
    return Counter(early_warning.replay(log).get("trigger_times", {}).get("private_channel", []))


def exp_channel(log, label, groups=(2, 3, 4), uses=(4, 6, 10), trials=20, window_h=6, seed=3):
    rng = random.Random(seed)
    agents = sorted({e.actor for e in log.events if e.actor and not str(e.actor).startswith("human:")})
    ts = sorted(e.ts for e in log.events if e.ts)
    lo, hi = ts[0], ts[-1] - window_h * 3600
    base = _pc_times(log)
    hours = (ts[-1] - ts[0]) / 3600
    bg_rate = sum(base.values()) / hours
    limit = early_warning.private_group_limit(getattr(log, "roster_size", None) or len(agents))
    rows = []
    for g in groups:
        for n in uses:
            det, delays = 0, []
            for t in range(trials):
                grp = rng.sample(agents, g)
                start = rng.uniform(lo, hi)
                times = sorted(rng.uniform(start, start + window_h * 3600) for _ in range(n))
                rid = f"planted_{g}_{n}_{t}.bin"
                extra = [ev(i, grp[i % g], tt, refs={"file": [rid]}) for i, tt in enumerate(times)]
                new = _pc_times(with_events(log, extra)) - base
                hits = sorted(x for x in new.elements() if x >= times[0] - 1)
                if hits:
                    det += 1
                    delays.append((hits[0] - times[0]) / 3600)
            rows.append(dict(log=label, group=g, uses=n, limit=limit, trials=trials, detected=det,
                             median_delay_h=round(statistics.median(delays), 2) if delays else None))
            print(f"  channel {label} g={g} n={n}: {det}/{trials}", file=sys.stderr)
    return dict(rows=rows, background_alerts_per_hour=round(bg_rate, 3), group_limit=limit)


# --------------------------------------------------------------------------
# 4. Hidden-channel flag rates: attack vs benign
# --------------------------------------------------------------------------
def exp_flags():
    logs = [("Swarm Traces (attack)", "swarm_traces")] + [
        (v, f"ai_village_{v}") for v in ("swarm-village", "game-jam-village", "open-chat-village", "main-village")]
    table = {}
    for label, d in logs:
        f = json.load(open(os.path.join(OUT, d, "findings.json")))
        n = f["summary"]["n_events"]
        table[label] = dict(n_events=n, per_1000={r["mechanism"]: round(1000 * r["n_events"] / n, 2)
                                                 for r in f["covert"]["inventory"]})
    return table


def main():
    t0 = time.time()
    res = {}
    print("loading swarm-village / open-chat ...", file=sys.stderr)
    sv, oc = village("swarm-village"), village("open-chat-village")
    res["spread"] = exp_spread(sv)
    res["channel"] = [exp_channel(sv, "swarm-village"), exp_channel(oc, "open-chat-village")]
    res["flags"] = exp_flags()
    print("loading Swarm Traces ...", file=sys.stderr)
    st = swarm_traces.load(os.path.join(DATA, "swarm-traces", "redacted.jsonl.gz"))
    res["ties"] = exp_ties(st)
    res["seconds"] = round(time.time() - t0)
    json.dump(res, open(os.path.join(OUT, "validation.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
