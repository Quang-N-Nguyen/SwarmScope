"""Early-warning replay: could the tool have flagged the swarm early?

We replay the events in time order and, at each step, use *only* information
seen so far (an online detector). We record the first moment each signal fires
and compare it with known milestones of the incident.

Two real-clock replays:

* **strict**   -- only events whose date was read from the data, and only
  agents who signed their work. Nothing inferred.
* **extended** -- also events with an inferred date and an inferred author
  (see ``swarmscope.infer``). More data, more risk of error.

The ``replay`` on the discovery order is kept for the viewer's markers only.
A held-out test showed that order is not a clock, so it is never used to
claim that something was "early".

Signals (all online, all cheap):

* ``shared_deaddrop``  -- first time any resource is touched by a 2nd distinct agent
* ``credential_reuse`` -- first time any credential appears in a 2nd event
* ``board``            -- first shared message-board / mailbox write
* ``duplicate_control``-- first lock / rival-kill (the swarm managing itself)
* ``signed_cmd``       -- first signed command (authenticated control plane)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from ..events import EventLog
from ..graph import _CHANNEL_REF_TYPES


# A "private channel" is shared by 2..PRIVATE_MAX_AGENTS agents and has at
# least PRIVATE_MIN_EVENTS attributed events. Small numbers on purpose: they
# describe a closed group talking repeatedly, not a public space.
PRIVATE_MAX_AGENTS = 3
PRIVATE_MIN_EVENTS = 6
# The group must also be small compared with the swarm: at most
# PRIVATE_MAX_SHARE of the swarm. In a 6-agent team, 2 agents are a third of
# everyone, so a file they share is not "private" (game-jam-village fired 97
# times without this rule). Example: 6 agents -> limit 0 (signal off);
# 25 agents -> 2; 30 or more -> 3.
# Swarm size = the roster size when the log has one (a deployer knows how many
# agents it runs; AI Village lists them). Without a roster we cannot count
# the swarm: in redacted Swarm Traces only 9 named agents are visible when the
# first private channel appears, although the swarm was far larger. Then we
# assume a large swarm (UNKNOWN_SWARM_SIZE) and keep the limit of 3.
PRIVATE_MAX_SHARE = 0.10
UNKNOWN_SWARM_SIZE = 30


def private_group_limit(n_agents: int) -> int:
    """Largest group that still counts as a private channel in a swarm of n agents."""
    return min(PRIVATE_MAX_AGENTS, int(PRIVATE_MAX_SHARE * n_agents))

# Signals that imply more than one agent and feed the combined alert.
# "private_channel" uses structure only; "board" uses the swarm's own message
# format (zz-prefixed entries), which an investigator would only know in hindsight.
ALERT_SIGNALS = ("private_channel", "board")


def _resources_of(e) -> List[str]:
    res = []
    if e.channel:
        res.append(e.channel)
    for rt in _CHANNEL_REF_TYPES:
        res += [f"{rt}:{rid}" for rid in e.ref_list(rt)]
    return res


def replay(log: EventLog, prefer_time: bool = True) -> dict:
    ordered = log.sorted_events(prefer_time)
    n = len(ordered) or 1

    res_agents: Dict[str, set] = defaultdict(set)   # resource -> agents seen
    res_n: Dict[str, int] = defaultdict(int)        # resource -> events so far
    res_task: Dict[str, int] = defaultdict(int)     # resource -> task-API events so far
    res_attr: Dict[str, int] = defaultdict(int)     # resource -> attributed events so far
    cred_events: Dict[str, int] = defaultdict(int)  # credential -> event count
    first_fire: Dict[str, dict] = {}
    reach_curve: List[dict] = []
    shared_dd = 0
    cum_pairs = 0
    agents_seen: set = set()
    roster = getattr(log, "roster_size", None)

    # Every distinct trigger, not just the first: (signal -> set of keys).
    # The count is what an analyst would have to review, i.e. the alert load.
    triggers: Dict[str, set] = defaultdict(set)
    trigger_times: Dict[str, list] = defaultdict(list)   # time of each new trigger (for the combined score)

    def fire(sig, pos, e, key=None):
        k_ = key if key is not None else e.event_id
        if k_ not in triggers[sig] and e.ts is not None:
            trigger_times[sig].append(round(e.ts))
        triggers[sig].add(k_)
        if sig not in first_fire:
            first_fire[sig] = dict(pos=pos, frac=round(pos / n, 4),
                                   event_id=e.event_id, ts=e.ts)

    for pos, e in enumerate(ordered):
        if e.actor and not str(e.actor).startswith("human:"):
            agents_seen.add(e.actor)
        limit = private_group_limit(max(len(agents_seen), roster or UNKNOWN_SWARM_SIZE))
        # shared dead-drop
        for r in set(_resources_of(e)):
            before = len(res_agents[r])
            res_n[r] += 1
            if e.has("task_submit"):
                res_task[r] += 1
            if e.actor:
                res_agents[r].add(e.actor)
                res_attr[r] += 1
            # Private persistent channel: a non-task resource used repeatedly by
            # a small closed group. A public room fails this because many
            # agents show up quickly; a two-agent dead-drop passes it.
            k = len(res_agents[r])
            if (2 <= k <= limit and res_attr[r] >= PRIVATE_MIN_EVENTS
                    and res_task[r] / res_n[r] < 0.5):
                fire("private_channel", pos, e, key=r)
            if before < 2 <= len(res_agents[r]):
                shared_dd += 1
                fire("shared_deaddrop", pos, e, key=r)
                # Same signal, but only if what we have seen of this resource
                # so far is mostly NOT the task's own API. Uses past data only.
                if res_task[r] / res_n[r] < 0.5:
                    fire("shared_deaddrop_nontask", pos, e, key=r)
        # credential reuse
        for c in e.ref_list("credential"):
            cred_events[c] += 1
            if cred_events[c] == 2:
                fire("credential_reuse", pos, e, key=c)
        # board / mailbox
        if e.has("board_token") or e.has("mailbox"):
            fire("board", pos, e)
        if e.has("lock_dupctrl") and (e.has("board_token") or e.has("mailbox")):
            fire("duplicate_control", pos, e)
        if e.has("signed_cmd"):
            fire("signed_cmd", pos, e)

        if pos % max(1, n // 400) == 0:
            reach_curve.append(dict(pos=pos, frac=round(pos / n, 4),
                                    shared_deaddrops=shared_dd))

    # Combined alert = earliest signal that implies more than one agent. A
    # shared dead-drop needs two named agents; a board / mailbox is multi-agent
    # by construction. Credential reuse is reported on its own but kept out of
    # the alert, because one agent can reuse a secret.
    provable = [s for s in ALERT_SIGNALS if s in first_fire]
    if provable:
        first = min(first_fire[s]["pos"] for s in provable)
        alert = dict(pos=first, frac=round(first / n, 4),
                     rule="earliest of private persistent channel or shared board / mailbox")
        alert["activity_still_ahead_frac"] = round(1 - first / n, 4)
    else:
        alert = None

    return dict(
        axis=log.time_axis(prefer_time),
        n_events=n,
        per_signal_first_fire=first_fire,
        triggers={s: len(v) for s, v in triggers.items()},
        trigger_times={s: sorted(v)[:20000] for s, v in trigger_times.items()},
        combined_first_alert=alert,
        total_shared_deaddrops=shared_dd,
        reach_curve=reach_curve,
    )


def timestamp_crosscheck(log: EventLog, include_inferred: bool = False) -> dict:
    """Replay on the real clock (see module docstring: strict vs extended).

    Strict (``include_inferred=False``): events with a date read from the
    data (``ts_source == "embedded"``) and signed authors only.
    Extended: also chain-inherited and inferred dates, and inferred authors.
    """
    import dataclasses
    # "native" = the log's own timestamps (attributed logs such as AI Village).
    ok = ("embedded", "native", "chain", "inferred") if include_inferred else ("embedded", "native")
    timed = [e for e in log.events if e.ts is not None and e.ts_source in ok]
    if len(timed) < 20:
        return dict(n_timed=len(timed), note="too few timestamped events for a time-based check")
    # Copy the events (never mutate the main log): clear the discovery key so
    # the sub-log sorts on the real clock, and in extended mode use the
    # inferred author where there is no observed one.
    copies = [dataclasses.replace(e, order_hint=None, seq=i,
                                  actor=(e.who(True) if include_inferred else e.actor))
              for i, e in enumerate(sorted(timed, key=lambda e: e.ts))]
    sub = EventLog(copies, name="timed")
    sub.roster_size = getattr(log, "roster_size", None)     # keep the swarm size for the private-channel limit
    r = replay(sub, prefer_time=True)
    milestones = getattr(log, "milestones", {}) or {}
    import datetime as _dt
    def _fmt(ts):
        if not ts:
            return None
        return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hours = (copies[-1].ts - copies[0].ts) / 3600 or 1.0
    out = dict(n_timed=len(timed), axis="time", include_inferred=include_inferred, signals={},
               hours=round(hours, 1),
               triggers=r.get("triggers", {}),
               trigger_times=r.get("trigger_times", {}),
               triggers_per_hour={k: round(v / hours, 2) for k, v in r.get("triggers", {}).items()})
    by_id = {e.event_id: e for e in copies}
    for s, v in r["per_signal_first_fire"].items():
        ev = by_id.get(v["event_id"])
        out["signals"][s] = dict(frac=v["frac"], when=_fmt(v["ts"]), ts=v["ts"],
                                 precision=(ev.ts_precision if ev else None),
                                 event_id=v["event_id"])

    # Lead time: hours between the first multi-agent alert and each milestone.
    alert_ts = None
    for s in ALERT_SIGNALS:
        v = r["per_signal_first_fire"].get(s)
        if v and v["ts"] is not None:
            alert_ts = v["ts"] if alert_ts is None else min(alert_ts, v["ts"])
    out["first_alert_when"] = _fmt(alert_ts)
    if alert_ts is not None and milestones:
        out["lead_hours"] = {name: round((ts - alert_ts) / 3600.0, 1)
                             for name, ts in sorted(milestones.items(), key=lambda x: x[1])}
        # Lead time per signal, so a reader can see which signal buys the most time.
        # "board" needs to know the swarm's own message format (hindsight);
        # "shared_deaddrop_nontask" uses only structure.
        per = {}
        for s, v in r["per_signal_first_fire"].items():
            if v["ts"] is None:
                continue
            per[s] = {name: round((ts - v["ts"]) / 3600.0, 1)
                      for name, ts in milestones.items()
                      if name in ("hf_credentials_found", "hf_worker_rce", "public_discovery")}
        out["lead_hours_by_signal"] = per
        # how much dated activity came after the alert
        after = sum(1 for e in copies if e.ts >= alert_ts)
        out["dated_activity_after_alert_frac"] = round(after / len(copies), 4)

    # daily volume of dated events, for a simple timeline chart
    daily = {}
    for e in copies:
        d = _dt.datetime.fromtimestamp(e.ts, _dt.timezone.utc).strftime("%Y-%m-%d")
        daily[d] = daily.get(d, 0) + 1
    out["daily_counts"] = sorted(daily.items())
    return out


def run_all(log: EventLog, prefer_time: bool = True) -> dict:
    return dict(replay=replay(log, prefer_time),
                timestamp_crosscheck=timestamp_crosscheck(log, include_inferred=False),
                extended=timestamp_crosscheck(log, include_inferred=True))
