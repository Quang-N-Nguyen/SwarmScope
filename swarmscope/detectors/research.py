"""Metrics that multi-agent safety researchers ask for.

Each function maps to a question from the reading list:

* ``validated_ties``  -- Is a tie between two agents more than chance?
  (statistically validated networks, Tumminello et al., 2011; collusion,
  Hammond et al., 2025)
* ``tactics``         -- What did each agent do, mapped to MITRE ATT&CK, and
  did the *group* cover more steps than any single agent? (patchwork
  capability, Tomasev et al., 2025; emergent agency, Hammond et al., 2025)
* ``who_when``        -- Which agent first did each step, and when?
  (failure attribution, Zhang et al., 2025)
* ``leaders_brokers`` -- Who moves first and who connects groups?
  (leader-follower / Stackelberg structure; mediators; Brandes, 2001)
* ``audit_budget``    -- If you can audit only k agents, how much of the
  coordination do you catch? (auditing budget, Greenblatt et al., 2024)
* ``cascades``        -- How far and how fast did an item spread?
  (network effects, Hammond et al., 2025)
* ``bursts``          -- Hours with unusual activity (destabilising dynamics).
* ``board_file_spread`` -- Who published a shared file and who used it later.

All functions use only the standard library and return plain dicts.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict, deque
from typing import Dict, List, Optional, Set, Tuple

from ..events import EventLog
from ..graph import _CHANNEL_REF_TYPES

# --------------------------------------------------------------------------
# Mechanism flag -> MITRE ATT&CK (https://attack.mitre.org/). Flags that have
# no ATT&CK technique are marked "SwarmScope" and named in plain words.
# --------------------------------------------------------------------------
TACTICS = {
    "k8s":                ("Discovery", "T1613", "Container and Resource Discovery"),
    "loot":               ("Credential Access", "T1552", "Unsecured Credentials"),
    "credential_use":     ("Credential use", "T1078", "Valid Accounts"),
    "board_token":        ("Command and Control", "T1102.001", "Dead Drop Resolver"),
    "mailbox":            ("Command and Control", "T1102.001", "Dead Drop Resolver"),
    "image_exfil":        ("Command and Control", "T1102", "Web Service"),
    "tunnel":             ("Command and Control", "T1572", "Protocol Tunneling"),
    "signed_cmd":         ("Command and Control", "SwarmScope", "Signed controller commands"),
    "container_registry": ("Persistence", "T1525", "Implant Internal Image"),
    "dns_exfil":          ("Exfiltration", "T1048", "Exfiltration Over Alternative Protocol"),
    "shortener_chain":    ("Stealth / Defense Evasion", "T1027", "Obfuscated Files or Information"),
    "cleanup":            ("Stealth / Defense Evasion", "T1070", "Indicator Removal"),
    "lock_dupctrl":       ("Swarm self-management", "SwarmScope", "Elections, locks, killing rival controllers"),
    "eval_target":        ("Evaluation tampering", "SwarmScope", "Targets the benchmark or scorer"),
    "external_llm":       ("Outside model use", "SwarmScope", "Calls outside language models"),
}
TACTIC_ORDER = ["Discovery", "Credential Access", "Credential use", "Command and Control",
                "Persistence", "Exfiltration", "Stealth / Defense Evasion",
                "Swarm self-management", "Evaluation tampering", "Outside model use"]


def _team_resources(e) -> List[str]:
    res = []
    if e.channel:
        res.append(e.channel)
    for rt in _CHANNEL_REF_TYPES:
        res += [f"{rt}:{rid}" for rid in e.ref_list(rt)]
    return res


# --------------------------------------------------------------------------
# 1. Statistically validated ties
# --------------------------------------------------------------------------
def _binom_pmf_upto(c: int, q: float, kmax: int) -> List[float]:
    """P(Binomial(c, q) = k) for k = 0..kmax."""
    out = [0.0] * (kmax + 1)
    if q <= 0.0:
        out[0] = 1.0
        return out
    if q >= 1.0:
        if c <= kmax:
            out[c] = 1.0
        return out
    lq, l1q = math.log(q), math.log1p(-q)
    for k in range(0, min(c, kmax) + 1):
        lc = math.lgamma(c + 1) - math.lgamma(k + 1) - math.lgamma(c - k + 1)
        out[k] = math.exp(lc + k * lq + (c - k) * l1q)
    return out


def shared_sf(x: int, groups: List[Tuple[int, float]]) -> float:
    """P(shared >= x) when each resource is shared independently.

    ``groups`` is a list of (number of resources, share probability). The sum
    of independent yes/no shares is a Poisson-binomial; we build it group by
    group and keep only totals below x (that is all we need).
    """
    if x <= 0:
        return 1.0
    dist = [1.0] + [0.0] * (x - 1)            # P(total = k), k < x
    for c, q in groups:
        pmf = _binom_pmf_upto(c, q, x - 1)
        new = [0.0] * x
        for i, pi in enumerate(dist):
            if pi == 0.0:
                continue
            for k in range(0, x - i):
                if pmf[k]:
                    new[i + k] += pi * pmf[k]
        dist = new
    return max(0.0, 1.0 - sum(dist))


def validated_ties(log: EventLog, alpha: float = 0.05, use_inferred: bool = False,
                   task_api_max: float = 0.5) -> dict:
    """Agent pairs that share more resources than chance allows.

    Steps:
    1. Build the agent x resource table. Drop resources where at least half of
       the events are ordinary task-API calls (everyone was given those).
    2. Null model that respects popularity on both sides (the idea behind the
       stochastic degree sequence model, Neal 2014, with the Chung-Lu 2002
       approximation): agent a uses resource r with probability
       p(a, r) = min(1, k_a * d_r / E), where k_a = resources a uses,
       d_r = agents using r, E = total agent-resource links. Each resource is
       shared with probability p(a, r) * p(b, r), independently, so the
       number shared follows a Poisson-binomial distribution, computed
       exactly by ``shared_sf``.
       Why: a plain hypergeometric test treats every resource as equally
       likely, so two agents that both use a hub (used by 70 agents) look
       "significant". This null expects hubs to be shared.
    3. Control the false discovery rate with Benjamini-Hochberg over all
       possible pairs (not only the pairs that share something), at ``alpha``.

    Example: a and b each use 4 resources, all rare (d_r = 2), with E = 400
    and 300 such resources. Then p = 4 * 2 / 400 = 0.02, each resource is
    shared with probability 0.02 * 0.02 = 0.0004, and about
    300 * 0.0004 = 0.12 shared resources are expected. Sharing 3 has
    probability about 0.0003.

    Power (tests/test_synthetic.py, 30 agents): a colluding pair is found
    in 20 of 20 runs when it shares 8 private resources, 4 of 20 at 6, and
    0 of 20 at 5 or fewer. No false ties in any run. A cautious test.
    """
    res_events: Counter = Counter()
    res_task: Counter = Counter()
    agent_res: Dict[str, Set[str]] = defaultdict(set)
    for e in log.events:
        rs = set(_team_resources(e))
        for r in rs:
            res_events[r] += 1
            if e.has("task_submit"):
                res_task[r] += 1
        who = e.who(use_inferred)
        if who:
            agent_res[who] |= rs
    keep = {r for r in res_events if res_task[r] / res_events[r] < task_api_max}
    dropped = len({r for rs in agent_res.values() for r in rs} - keep)
    agent_res = {a: rs & keep for a, rs in agent_res.items() if rs & keep}
    N = len({r for rs in agent_res.values() for r in rs})
    agents = sorted(agent_res)
    holders: Dict[str, List[str]] = defaultdict(list)
    for a, rs in agent_res.items():
        for r in rs:
            holders[r].append(a)
    shared: Counter = Counter()
    for r, hs in holders.items():
        hs = sorted(hs)
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                shared[(hs[i], hs[j])] += 1
    m = len(agents) * (len(agents) - 1) // 2 or 1
    # resource popularity, grouped by degree so mu is cheap to compute
    deg_count: Counter = Counter(len(hs) for hs in holders.values())
    E = sum(d * c for d, c in deg_count.items()) or 1

    def groups(ka: int, kb: int) -> List[Tuple[int, float]]:
        # sorted: a fixed summation order, so p-values are identical on every run
        return [(c, min(1.0, ka * d / E) * min(1.0, kb * d / E)) for d, c in sorted(deg_count.items())]

    tests = []
    for (a, b), x in shared.items():
        p = shared_sf(x, groups(len(agent_res[a]), len(agent_res[b])))
        tests.append((p, a, b, x))
    tests.sort()
    # Benjamini-Hochberg: largest rank i with p_i <= alpha * i / m
    cut = 0
    for i, (p, *_rest) in enumerate(tests, start=1):
        if p <= alpha * i / m:
            cut = i
    validated = [dict(a=a, b=b, shared=x, p=float(f"{p:.3g}")) for p, a, b, x in tests[:cut]]
    ks = sorted(len(r) for r in agent_res.values())
    return dict(agents=len(agents), resources=N, resources_dropped_as_task_api=dropped,
                pairs_tested=m, pairs_sharing_any=len(shared), validated=len(validated),
                alpha=alpha, ties=validated,
                # power check: the best pair's p-value vs the bar for rank 1
                min_p=float(f"{tests[0][0]:.3g}") if tests else None,
                bar_for_best_pair=float(f"{alpha / m:.3g}"),
                median_resources_per_agent=ks[len(ks) // 2] if ks else 0,
                best_pairs=[dict(a=a, b=b, shared=x, p=float(f"{p:.3g}")) for p, a, b, x in tests[:5]])


# --------------------------------------------------------------------------
# 2. Tactics, roles, and patchwork capability
# --------------------------------------------------------------------------
def tactics(log: EventLog, use_inferred: bool = True) -> dict:
    """Per-agent ATT&CK tactic profile, roles, and group-vs-individual coverage.

    * role: the tactic with most of the agent's events (ties go to the tactic
      listed first in TACTIC_ORDER, so the result does not depend on set order)
    * specialisation: 1 - entropy / max entropy (1 = one tactic only, 0 = even mix)
    * patchwork: tactics covered by the group vs by the best single agent, and
      the fewest agents that together cover everything (greedy set cover)
    """
    per_agent: Dict[str, Counter] = defaultdict(Counter)
    tactic_agents: Dict[str, Set[str]] = defaultdict(set)
    tactic_events: Counter = Counter()
    for e in log.events:
        who = e.who(use_inferred)
        ts, ts_agent = set(), set()
        for f, (tac, _, _) in TACTICS.items():
            if e.has(f):
                ts.add(tac)
                # The board-token flag is how agents get their names, so every
                # named agent has it. Counting it would give everyone a
                # Command-and-Control role by construction; leave it out of
                # the per-agent profile (it still counts in the event totals).
                if f != "board_token":
                    ts_agent.add(tac)
        for tac in ts:
            tactic_events[tac] += 1
        if who:
            for tac in ts_agent:
                per_agent[who][tac] += 1
                tactic_agents[tac].add(who)
    roles = {}
    for a, c in per_agent.items():
        tot = sum(c.values())
        k = len(TACTIC_ORDER)
        ent = -sum((v / tot) * math.log(v / tot) for v in c.values())
        roles[a] = dict(role=min(c, key=lambda t: (-c[t], TACTIC_ORDER.index(t))),
                        specialisation=round(1 - ent / math.log(k), 3),
                        tactics=sorted(c, key=lambda t: TACTIC_ORDER.index(t)))
    group_cov = {t for t in TACTIC_ORDER if tactic_agents.get(t)}
    best_single = max((len(c) for c in per_agent.values()), default=0)
    # greedy set cover
    remaining, cover = set(group_cov), []
    sets = {a: set(c) for a, c in per_agent.items()}
    while remaining:
        a = max(sets, key=lambda x: len(sets[x] & remaining))
        gain = sets[a] & remaining
        if not gain:
            break
        cover.append(a)
        remaining -= gain
    role_counts = Counter(r["role"] for r in roles.values())
    table = []
    for t in TACTIC_ORDER:
        techs = sorted({(tid, nm) for f, (tac, tid, nm) in TACTICS.items() if tac == t})
        table.append(dict(tactic=t, techniques=[f"{tid} {nm}" for tid, nm in techs],
                          events=tactic_events.get(t, 0), agents=len(tactic_agents.get(t, ()))))
    return dict(table=table, roles=roles, role_counts=role_counts.most_common(),
                group_tactics=len(group_cov), best_single_agent_tactics=best_single,
                min_agents_to_cover_all=len(cover), cover_set=cover,
                mean_specialisation=round(sum(r["specialisation"] for r in roles.values()) / len(roles), 3) if roles else None)


# --------------------------------------------------------------------------
# 3. Who and when
# --------------------------------------------------------------------------
def who_when(log: EventLog) -> List[dict]:
    """For each tactic: the first dated event, its time, and its author.

    Uses only real-clock times. Reports both the first time read from the data
    and the first time including inferred dates, so you can see the gap.
    """
    rows = []
    timed = log.timed_events(include_inferred=True)
    for t in TACTIC_ORDER:
        flags = [f for f, (tac, _, _) in TACTICS.items() if tac == t]
        first_obs = first_any = None
        for e in timed:
            if any(e.has(f) for f in flags):
                if first_any is None:
                    first_any = e
                if e.ts_source != "inferred" and first_obs is None:
                    first_obs = e
                if first_obs is not None:
                    break
        def _fmt(e):
            if e is None:
                return None
            return dict(event_id=e.event_id, ts=e.ts, ts_source=e.ts_source,
                        who=e.actor or (e.actor_inferred and e.actor_inferred + " (inferred)") or e.persona or "unknown")
        rows.append(dict(tactic=t, first_observed=_fmt(first_obs), first_incl_inferred=_fmt(first_any)))
    return rows


# --------------------------------------------------------------------------
# 4. Leaders and brokers
# --------------------------------------------------------------------------
def _betweenness(nodes: List[str], adj: Dict[str, Set[str]]) -> Dict[str, float]:
    """Brandes (2001) betweenness for an unweighted, undirected graph."""
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack, pred = [], defaultdict(list)
        sigma = dict.fromkeys(nodes, 0); sigma[s] = 1
        dist = dict.fromkeys(nodes, -1); dist[s] = 0
        q = deque([s])
        while q:
            v = q.popleft(); stack.append(v)
            for w in adj.get(v, ()):
                if dist[w] < 0:
                    dist[w] = dist[v] + 1; q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]; pred[w].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    n = len(nodes)
    norm = (n - 1) * (n - 2) if n > 2 else 1
    return {k: v / norm for k, v in bc.items()}   # undirected: sum counts each pair twice


def leaders_brokers(log: EventLog, ties: List[dict], use_inferred: bool = True, top: int = 15) -> dict:
    """Leaders: who touches shared resources first (on the real clock).

    For every team resource used by 2+ agents with dated events, the first
    agent "leads" and each later agent "follows". Leader score = number of
    (resource, follower) pairs led. We also report the median lag in hours.

    Brokers: betweenness centrality on the validated-tie graph, i.e. agents
    that sit on the shortest paths between other agents.
    """
    first: Dict[str, Dict[str, float]] = defaultdict(dict)
    for e in log.timed_events(include_inferred=True):
        who = e.who(use_inferred)
        if not who:
            continue
        for r in _team_resources(e):
            if who not in first[r]:
                first[r][who] = e.ts
    lead, follow = Counter(), Counter()
    lags: Dict[str, List[float]] = defaultdict(list)
    for r, d in first.items():
        if len(d) < 2:
            continue
        order = sorted(d.items(), key=lambda x: x[1])
        leader, t0 = order[0]
        for a, t in order[1:]:
            lead[leader] += 1
            follow[a] += 1
            lags[leader].append((t - t0) / 3600)
    leaders = [dict(agent=a, led=n, followed=follow.get(a, 0),
                    median_lag_hours=round(sorted(lags[a])[len(lags[a]) // 2], 2))
               for a, n in lead.most_common(top)]
    adj: Dict[str, Set[str]] = defaultdict(set)
    for t in ties:
        adj[t["a"]].add(t["b"]); adj[t["b"]].add(t["a"])
    nodes = sorted(adj)
    bc = _betweenness(nodes, adj) if nodes else {}
    brokers = [dict(agent=a, betweenness=round(v, 4), degree=len(adj[a]))
               for a, v in sorted(bc.items(), key=lambda x: -x[1])[:top] if v > 0]
    return dict(leaders=leaders, brokers=brokers,
                resources_with_order=sum(1 for d in first.values() if len(d) >= 2))


# --------------------------------------------------------------------------
# 5. Audit budget
# --------------------------------------------------------------------------
_SUSPICIOUS = ("board_token", "mailbox", "signed_cmd", "lock_dupctrl", "dns_exfil",
               "image_exfil", "tunnel", "cleanup", "loot", "k8s", "container_registry")


def audit_budget(log: EventLog, ties: List[dict], use_inferred: bool = True) -> dict:
    """How many agents must a human audit to cover most of the coordination?

    Rank agents by a simple suspicion score: the number of their events with a
    covert mechanism flag (not counting credential use or task calls). Then
    walk down the ranking and measure, after k audited agents, the share of
    validated ties that touch at least one audited agent. The ties are an
    independent signal (they come from shared resources, not from the flags),
    so this is a fair check of the ranking.
    """
    score: Counter = Counter()
    for e in log.events:
        who = e.who(use_inferred)
        if who:
            score[who] += sum(1 for f in _SUSPICIOUS if e.has(f))
    ranked = [a for a, _ in score.most_common()]
    tie_set = [(t["a"], t["b"]) for t in ties]
    curve = []
    audited: Set[str] = set()
    need = {}
    for k, a in enumerate(ranked, start=1):
        audited.add(a)
        cov = (sum(1 for x, y in tie_set if x in audited or y in audited) / len(tie_set)) if tie_set else 0.0
        curve.append(round(cov, 4))
        for target in (0.5, 0.8, 0.95):
            if cov >= target and target not in need:
                need[target] = k
    n = len(ranked)
    return dict(agents_ranked=n, ties=len(tie_set),
                agents_needed={f"{int(t*100)}%": (v, round(v / n, 3)) for t, v in need.items()} if n else {},
                curve=curve, top_suspects=score.most_common(15))


# --------------------------------------------------------------------------
# 6. Cascades
# --------------------------------------------------------------------------
def cascades(log: EventLog, communities: Optional[Dict[str, int]] = None,
             ref_types=("credential", "destination"), top: int = 8, use_inferred: bool = True) -> List[dict]:
    """How far and how fast did each information item spread (real clock)?

    For each credential or dead-drop dataset: the first agent, how many agents
    it reached, hours from first to last use, hours until half of those agents
    had used it, and how many agent communities it reached.

    Each row also carries a transmission tree for the viewer: ``times`` is the
    first-use time of every agent in order, and ``tree`` lists one
    ``(parent, adopter)`` pair per later agent, where the parent is the latest
    earlier user (a dead-drop shows no address, so this is the best guess, as
    in the fallback rule of :mod:`diffusion`). ``inferred`` says, per adopter,
    whether its name was inferred rather than read from the data.

    Example: A uses credential 7 at 10:00, B at 10:05, C at 10:30 ->
    ``tree = [("A", "B"), ("B", "C")]``, ``times = [10:00, 10:05, 10:30]``.
    """
    touches: Dict[str, List[Tuple[float, str, bool]]] = defaultdict(list)
    for e in log.timed_events(include_inferred=True):
        who = e.who(use_inferred)
        if not who:
            continue
        inferred = e.actor is None
        for rt in ref_types:
            for rid in e.ref_list(rt):
                touches[f"{rt}:{rid}"].append((e.ts, who, inferred))
    rows = []
    for item, lst in touches.items():
        firsts: Dict[str, float] = {}
        first_inf: Dict[str, bool] = {}
        for t, a, inf in sorted(lst, key=lambda x: (x[0], x[1])):
            if a not in firsts:
                firsts[a] = t
                first_inf[a] = inf
        if len(firsts) < 2:
            continue
        order = sorted(firsts, key=lambda a: (firsts[a], a))
        times = [firsts[a] for a in order]
        t0 = times[0]
        half = times[(len(times) - 1) // 2]
        comms = {communities.get(f"agent:{a}") for a in firsts} if communities else set()
        rows.append(dict(item=item, origin=order[0], agents=len(firsts),
                         span_hours=round((times[-1] - t0) / 3600, 1),
                         hours_to_half=round((half - t0) / 3600, 1),
                         communities=len(comms - {None}) if comms else None,
                         times=times,
                         tree=[(order[i - 1], order[i]) for i in range(1, len(order))],
                         inferred=[first_inf[a] for a in order]))
    rows.sort(key=lambda r: (-r["agents"], r["span_hours"]))
    return rows[:top]


# --------------------------------------------------------------------------
# 7. Bursts on the real clock
# --------------------------------------------------------------------------
def bursts(log: EventLog, z: float = 3.0, top: int = 10) -> dict:
    """Hours whose event count is ``z`` standard deviations above the mean.

    Only clock-precise times count. A date with no time of day is stored as
    12:00 UTC, so hundreds of day-dated events would otherwise pile up into one
    fake "burst" at noon. An inferred time that sits exactly on 12:00:00 is
    treated the same way, because it was most likely copied from such a date.
    """
    hours: Counter = Counter()
    mech: Dict[int, Counter] = defaultdict(Counter)
    skipped = 0
    for e in log.timed_events(include_inferred=True):
        if not clock_precise(e):
            skipped += 1
            continue
        h = int(e.ts // 3600)
        hours[h] += 1
        for f in _SUSPICIOUS:
            if e.has(f):
                mech[h][f] += 1
    if len(hours) < 3:
        return dict(n_hours=len(hours), bursts=[], day_dated_skipped=skipped)
    lo, hi = min(hours), max(hours)
    series = [hours.get(h, 0) for h in range(lo, hi + 1)]
    mean = sum(series) / len(series)
    sd = (sum((x - mean) ** 2 for x in series) / len(series)) ** 0.5 or 1.0
    import datetime as _dt
    rows = []
    for h in range(lo, hi + 1):
        c = hours.get(h, 0)
        if (c - mean) / sd >= z:
            rows.append(dict(hour=_dt.datetime.fromtimestamp(h * 3600, _dt.timezone.utc).strftime("%Y-%m-%d %H:00 UTC"),
                             events=c, z=round((c - mean) / sd, 1),
                             top_mechanisms=mech[h].most_common(3)))
    rows.sort(key=lambda r: -r["z"])
    return dict(n_hours=len(series), mean_per_hour=round(mean, 2), bursts=rows[:top],
                day_dated_skipped=skipped)


def clock_precise(e) -> bool:
    """True when the event's time has a time of day, not only a date."""
    if e.ts is None or e.ts_precision == "day":
        return False
    if e.ts_precision == "inferred" and e.ts % 86400 == 43200:
        return False
    return True


# --------------------------------------------------------------------------
# 8. Shared board files: publisher -> later users
# --------------------------------------------------------------------------
def board_file_spread(log: EventLog, top: int = 10, use_inferred: bool = True) -> dict:
    """Files the agents shared on the board (zzFILE_* tokens).

    The handle inside the file name is the publisher (for example
    zzFILE_URI23816D_SUBMITJS_V2 was published by URI23816D). Every other
    event that references the same file token is a later use. This is the most
    direct "who passed what to whom" evidence in the data.
    """
    users: Dict[str, Set[str]] = defaultdict(set)
    events: Counter = Counter()
    publisher: Dict[str, str] = {}
    hand = re.compile(r"([A-Z]{2,}\d{2,}[A-Z]?)")
    for e in log.events:
        for tok in e.fingerprints.get("board_file", ()):
            events[tok] += 1
            m = hand.search(tok)
            if m:
                publisher.setdefault(tok, m.group(1))
            who = e.who(use_inferred)
            if who:
                users[tok].add(who)
    rows = []
    for tok, n in events.items():
        pub = publisher.get(tok)
        others = sorted(users[tok] - {pub})
        rows.append(dict(file=tok, publisher=pub, events=n, other_agents=len(others), others=others[:8]))
    rows.sort(key=lambda r: (-r["other_agents"], -r["events"]))
    return dict(files=len(rows), files_used_by_other_agents=sum(1 for r in rows if r["other_agents"]),
                top=rows[:top])


def run_all(log: EventLog, communities: Optional[Dict[str, int]] = None,
            strong_ties: Optional[List[dict]] = None) -> dict:
    """Run every metric.

    ``strong_ties`` (pairs with an Adamic-Adar score >= 1 from the agent
    projection) is used for brokers and the audit budget when the cautious
    statistical test validates too few ties to work with (< 10).
    """
    vt = validated_ties(log)
    vt_inf = validated_ties(log, use_inferred=True)
    if vt["validated"] >= 10 or not strong_ties:
        ties, tie_set = vt["ties"], "validated"
    else:
        ties, tie_set = strong_ties, "strong (Adamic-Adar >= 1)"
    return dict(
        validated_ties=vt,
        validated_ties_with_inferred=dict((k, v) for k, v in vt_inf.items() if k not in ("ties", "best_pairs")),
        tie_set_for_structure=tie_set,
        n_structure_ties=len(ties),
        tactics=tactics(log),
        who_when=who_when(log),
        leaders_brokers=leaders_brokers(log, ties),
        audit_budget=audit_budget(log, ties),
        cascades=cascades(log, communities),
        bursts=bursts(log),
        board_file_spread=board_file_spread(log),
    )
