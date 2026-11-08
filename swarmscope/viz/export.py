"""Shape graph + detector output into the JSON the HTML viewer reads, and
assemble the viewer HTML (D3 inlined for offline use, or loaded from a CDN for
a hosted page).

The viewer has two time axes:

* **Real clock** -- only events with a time (read from the data or inferred).
  Positions are unix seconds. Edges and nodes without a time are hidden.
* **Discovery order** -- every event, in the order the reconstruction found
  its resources. This is NOT a clock; it is only a way to browse everything.
"""

from __future__ import annotations

import datetime as _dt
import json
from html import escape as html_escape
import os
from collections import Counter, defaultdict
from typing import Dict, Optional

from ..events import EventLog
from ..graph import TemporalGraph, _label_propagation, build_activity_graph, build_agent_projection

_HERE = os.path.dirname(__file__)

_MILESTONE_LABELS = {
    "main_board_established": "Main board set up (METR)",
    "hf_credentials_found": "HF credentials found",
    "hf_file_read": "HF arbitrary file read",
    "hf_worker_rce": "RCE on HF worker",
    "coordinators_stopped": "Coordinators stopped",
    "hf_cut_access": "HF cut access",
    "public_discovery": "Found by outside researchers",
}


def _utc(ts):
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc)


def _forensics(log: EventLog, findings: dict) -> Optional[dict]:
    """Time series for the forensics charts (logs with named speakers only).

    * cp      -- change detector: z-scores of topic and volume every 10 min, alerts
    * claims  -- cumulative agents addressing each god-role claimant
    * spread  -- cumulative adopters of the top file, commit and coined term
    * roles   -- share of agent chat messages that mention "role", per 30 min
    """
    import re
    A = findings.get("attributed") or {}
    if not A:
        return None
    cp = A.get("changepoint") or {}
    out = dict(
        cp=dict(z=(cp.get("params") or {}).get("z"),
                series=[(r["t"], r["z_topic"], r["z_volume"]) for r in cp.get("series", [])],
                alerts=[a["t"] for a in cp.get("alerts", [])]),
        claims=[], spread=[], roles=[])
    for r in (A.get("authority") or {}).values():
        rows = sorted(r["claimants"], key=lambda c: -c["endorsers"])[:3]
        for c in rows:
            out["claims"].append(dict(name=c["agent"] + (" (assigned god)" if c["assigned"] else " (not assigned)"),
                                      times=c.get("endorsement_times", [])))
    df = A.get("diffusion") or {}
    for kind, label in (("files", "file"), ("commits", "commit"), ("terms", "term")):
        top = (df.get(kind) or [])[:1]
        for it in top:
            out["spread"].append(dict(name=f"{label} {it['item'][:24]}", times=it.get("times", [])))
    dl = cp.get("daily") or {}
    if dl.get("series"):
        out["daily"] = dict(series=dl["series"], alerts=dl.get("alert_days", []), z=dl["params"]["z"],
                            ref_days=dl["params"]["ref_days"], lag=dl["params"]["lag"], flagged=dl.get("flagged"),
                            milestones=dl.get("milestones"), recall=dl.get("recall"), chance=dl.get("chance"),
                            precision=dl.get("precision"))
    # long logs: thin the 10-minute series to at most ~3,000 points for the chart
    if len(out["cp"]["series"]) > 3000:
        k = len(out["cp"]["series"]) // 3000 + 1
        out["cp"]["series"] = out["cp"]["series"][::k]
    rd = ((A.get("actions") or {}).get("role_drift") or {})
    if rd.get("series"):
        out["drift"] = dict(series=[(t, n, m) for t, n, m in rd["series"] if n >= 3], alert=rd.get("alert"),
                            agents=rd.get("agents_drifted"), before=rd.get("before_alert"))
    if not ((A.get("diffusion") or {}).get("case_studies") or {}).get("role_confusion"):
        return out          # no role reassignment to look at: skip the role-talk chart
    rx = re.compile(r"\broles?\b")
    B = 1800
    buckets: Dict[int, list] = defaultdict(lambda: [0, 0])
    for e in log.timed_events():
        if e.kind == "chat" and e.actor and not e.actor.startswith("human:"):
            b = buckets[int(e.ts // B)]
            b[0] += 1
            if rx.search(e.meta.get("text_lc") or ""):
                b[1] += 1
    out["roles"] = [((k * B) + B / 2, round(v[1] / v[0], 3), v[0]) for k, v in sorted(buckets.items()) if v[0] >= 10]
    return out


def _cascades(findings: dict, per_kind: int = 3) -> list:
    """Transmission trees to animate on the graph: who probably passed an item
    to whom, and when. Edge i of a tree is the adoption at times[i + 1].

    Named-speaker logs (AI Village) give files, commits, coined terms and role
    claims. Redacted logs (Swarm Traces) give credentials and dead-drop
    datasets, from the real-clock spread table (``research.cascades``); an
    edge whose adopter was named by inference carries ``inf=True`` so the
    viewer can draw it dashed.
    """
    A = findings.get("attributed") or {}
    out = []

    def add(kind, label, origin, tree, times, inferred=None):
        if not tree or not times:
            return
        edges = [dict(s="agent:" + str(p), t="agent:" + str(c), ts=times[i + 1],
                      **({"inf": True} if inferred and i + 1 < len(inferred) and inferred[i + 1] else {}))
                 for i, (p, c) in enumerate(tree) if p and i + 1 < len(times)]
        out.append(dict(kind=kind, label=label, origin="agent:" + str(origin), first_ts=times[0],
                        reach=len(times), edges=edges))

    if not A:
        kinds = {"credential": "credential", "destination": "dead-drop"}
        for it in (findings.get("research") or {}).get("cascades") or []:
            rt, _, rid = it["item"].partition(":")
            add(kinds.get(rt, rt), it["item"], it["origin"], it.get("tree"), it.get("times"), it.get("inferred"))
        return out

    df = A.get("diffusion") or {}
    for kind, name in (("files", "file"), ("commits", "commit"), ("terms", "term")):
        for it in (df.get(kind) or [])[:per_kind]:
            add(name, it["item"], it["origin"], it.get("tree"), it.get("times"))
    # Claims: an edge from each agent to the claimant, when it first addressed
    # the claimant in that role (endorsement), starting at the claim.
    for role, r in (A.get("authority") or {}).items():
        for c in sorted(r.get("claimants", []), key=lambda c: -c["endorsers"])[:2]:
            uses = c.get("endorsement_uses") or []
            if not uses:
                continue
            out.append(dict(kind="claim", label=f"{c['agent']} as {role}" + (" (assigned)" if c["assigned"] else " (not assigned)"),
                            origin="agent:" + c["agent"], first_ts=c["first_claim"], reach=len(uses) + 1,
                            edges=[dict(s="agent:" + a, t="agent:" + c["agent"], ts=t) for t, a in uses]))
    return out


def _exchanges(log: EventLog, attributed: bool, prefer_time: bool = True,
               max_rows: int = 200_000) -> dict:
    """Agent-to-agent exchanges, one row each, for the animated arcs of the world viewer.

    * Named-speaker logs: ``A @-addressed B`` (one row per recipient).
    * Redacted logs: a dead-drop hand-off. When agent B uses a resource whose
      latest earlier user was agent A, that is a row A -> B (the same "latest
      earlier user" rule as "Follow an item"; an order, not proof that B read
      A's bytes).

    Returns ``{"agents": [node ids], "base": t0, "rows": [[dt, pos, i, j, inf]]}``:
    ``dt`` seconds after ``base`` (None without a date), ``pos`` the discovery
    position, ``i``/``j`` indexes into ``agents``, ``inf`` 1 when either end
    was named by inference. Ids and times only, never payload text.
    """
    from ..graph import _CHANNEL_REF_TYPES
    ordered = log.sorted_events(prefer_time)
    timed = [e.ts for e in ordered if e.ts is not None]
    base = min(timed) if timed else 0
    idx: Dict[str, int] = {}

    def ix(name):
        nid = "agent:" + name
        if nid not in idx:
            idx[nid] = len(idx)
        return idx[nid]

    rows = []
    last: Dict[str, tuple] = {}
    for pos, e in enumerate(ordered):
        dt = None if e.ts is None else round(e.ts - base)
        if attributed:
            if not e.actor:
                continue
            for r in dict.fromkeys(e.recipients):
                if r != e.actor:
                    rows.append([dt, pos, ix(e.actor), ix(r), 0])
            continue
        who = e.who(True)
        if not who:
            continue
        inf = 1 if e.actor is None else 0
        res = ([e.channel] if e.channel else []) + [f"{rt}:{x}" for rt in _CHANNEL_REF_TYPES for x in e.ref_list(rt)]
        done = set()
        for r in res:
            prev = last.get(r)
            if prev and prev[0] != who and prev[0] not in done:
                done.add(prev[0])
                rows.append([dt, pos, ix(prev[0]), ix(who), max(inf, prev[1])])
            last[r] = (who, inf)
    if len(rows) > max_rows:
        step = len(rows) / max_rows
        rows = [rows[int(i * step)] for i in range(max_rows)]
    return dict(agents=list(idx), base=base, rows=rows)


EVENTS_PER_AGENT = 200
_TRAIL_FLAGS = ("board_token", "mailbox", "image_exfil", "dns_exfil", "signed_cmd", "lock_dupctrl",
                "loot", "tunnel", "k8s", "container_registry", "cleanup", "external_llm", "credential_use",
                "eval_target", "task_submit")


def _agent_trails(log: EventLog, prefer_time: bool = True, per_agent: int = EVENTS_PER_AGENT) -> Dict[str, dict]:
    """``agent -> {"ev": rows, "n_ev": total}``: what each named agent did, in order.

    A row is ``[ts, pos, kind, target, recipients, flags, inferred]``:
    ``target`` is the channel or first shared resource the event touched,
    ``flags`` the mechanism flags that fired, ``inferred`` 1 when the author
    came from inference. More than ``per_agent`` events are thinned to an even
    sample (first and last kept), so a long history still shows its shape.
    """
    ordered = log.sorted_events(prefer_time)
    rows: Dict[str, list] = defaultdict(list)
    for pos, e in enumerate(ordered):
        who = e.who(True)
        if not who:
            continue
        target = e.channel
        if not target:
            refs = e.all_refs()
            target = refs[0] if refs else None
        flags = [f for f in _TRAIL_FLAGS if e.features.get(f)]
        rows[who].append([e.ts, pos, e.kind, target, e.recipients[:3], flags, 1 if e.actor is None else 0])
    out = {}
    for who, lst in rows.items():
        n = len(lst)
        if n > per_agent:
            step = (n - 1) / (per_agent - 1)
            lst = [lst[round(i * step)] for i in range(per_agent)]
        out[who] = dict(ev=lst, n_ev=n)
    return out


def build_graph_data(log: EventLog, findings: Optional[dict] = None,
                     prefer_time: bool = True, top_resources: int = 120) -> dict:
    findings = findings or {}
    act = build_activity_graph(log, prefer_time, top_resources=top_resources, use_inferred=True)
    proj, comms = build_agent_projection(log, prefer_time)
    res = findings.get("research", {})
    roles = res.get("tactics", {}).get("roles", {})
    leaders = {x["agent"]: x for x in res.get("leaders_brokers", {}).get("leaders", [])}
    brokers = {x["agent"]: x["betweenness"] for x in res.get("leaders_brokers", {}).get("brokers", [])}

    maxpos = max([n["last_pos"] for n in act.nodes.values()] + [1])

    # Named-speaker logs: all agents share one public room, so communities are
    # trivial (one group). Colour by authority status instead and show each
    # agent's assigned role: 0 = other, 1 = claimed a privileged role it was
    # not given, 2 = assigned holder of that role.
    attributed = bool(findings.get("attributed"))
    status: Dict[str, int] = {}
    goal_now: Dict[str, str] = {}
    priv_role = None    # the privileged role the authority detector checked (e.g. "god")
    if attributed:
        priv_role = next(iter(sorted(findings["attributed"].get("authority") or {})), None)
        for r in (findings["attributed"].get("authority") or {}).values():
            for c in r["claimants"]:
                status["agent:" + c["agent"]] = 2 if c["assigned"] else 1
        for a, gl in (getattr(log, "agent_goals", {}) or {}).items():
            if gl:
                goal_now["agent:" + a] = gl[-1][1].split("—")[0].strip()[:40]

    # ---- what each agent did: a short event list per agent node
    # [ts, pos, kind, target, recipients, flags, inferred]. Long histories are
    # thinned to an even sample of EVENTS_PER_AGENT rows; ``n_ev`` keeps the
    # true count. Only ids, kinds and flags: never the text of a payload.
    trail = _agent_trails(log, prefer_time)

    # ---- nodes
    nodes = []
    for nid, n in act.nodes.items():
        comm = comms.get(nid)
        lab = n["label"]
        r = roles.get(lab, {}) if n["type"] == "agent" else {}
        ld = leaders.get(lab, {})
        if attributed and n["type"] == "agent":
            comm = status.get(nid, 0)
            r = dict(role=goal_now.get(nid))
        nodes.append(dict(
            id=nid, ty=n["type"], lab=lab, c=n["count"],
            p0=n["first_pos"], pn=n["last_pos"], t0=n["first_ts"], tn=n["last_ts"],
            comm=(comm if comm is not None else -1),
            mech=[m for m, _ in n["features"].most_common(3)],
            obs=n.get("obs"), inf=n.get("inf"),
            role=r.get("role"), spec=r.get("specialisation"), tac=r.get("tactics"),
            led=ld.get("led"), fol=ld.get("followed"), betw=brokers.get(lab),
            **(trail.get(lab) or {})))

    # ---- activity edges, aggregated by (src, dst, kind)
    agg: Dict[tuple, dict] = {}
    for e in act.edges:
        key = (e["src"], e["dst"], e["kind"])
        a = agg.get(key)
        if a is None:
            a = agg[key] = dict(s=e["src"], t=e["dst"], k=e["kind"], p0=e["pos"], pn=e["pos"],
                                t0=None, tn=None, w=0, inf=True)
        a["p0"] = min(a["p0"], e["pos"]); a["pn"] = max(a["pn"], e["pos"]); a["w"] += 1
        if e.get("ts") is not None:
            a["t0"] = e["ts"] if a["t0"] is None else min(a["t0"], e["ts"])
            a["tn"] = e["ts"] if a["tn"] is None else max(a["tn"], e["ts"])
        if not e.get("inf"):
            a["inf"] = False          # at least one observed event backs this edge
    links = list(agg.values())

    # ---- agent-agent edges
    if attributed:
        # Named speakers: the edge is "A @-addressed B" (both directions
        # counted together), weight = number of addresses, t0 = first one.
        pos_of = {e.event_id: i for i, e in enumerate(log.sorted_events(prefer_time))}
        pairs: Dict[tuple, dict] = {}
        for e in log.events:
            if not e.actor or e.actor.startswith("human:"):
                continue
            for r in e.recipients:
                if r == e.actor:
                    continue
                key = tuple(sorted((e.actor, r)))
                p = pairs.setdefault(key, dict(s="agent:" + key[0], t="agent:" + key[1],
                                               p0=pos_of.get(e.event_id, 0), t0=e.ts, w=0))
                p["w"] += 1
                if e.ts is not None and (p["t0"] is None or e.ts < p["t0"]):
                    p["t0"], p["p0"] = e.ts, pos_of.get(e.event_id, p["p0"])
        proj_links = list(pairs.values())
    else:
        proj_links = [dict(s=e["src"], t=e["dst"], p0=e["pos"], t0=e.get("ts"),
                           w=e.get("weight", 1)) for e in proj.edges]

    # ---- islands for the world view: the paper's communities (label
    # propagation, Raghavan et al. 2007) on the same agent graph the viewer
    # draws. Redacted logs: the shared-resource projection's communities.
    # Named logs: the @-address graph. -1 = no ties.
    if attributed:
        ag = TemporalGraph()
        for l in proj_links:
            for x in (l["s"], l["t"]):
                if x not in ag.nodes:
                    ag.add_node(x, "agent", x, 0, None)
            ag.add_edge(l["s"], l["t"], "coordinate", 0, None, "a")
            ag.edges[-1]["weight"] = l["w"]
        groups = _label_propagation(ag)
    else:
        groups = comms
    linked = {x for l in proj_links for x in (l["s"], l["t"])}
    for nd in nodes:
        if nd["ty"] == "agent":
            nd["grp"] = groups.get(nd["id"], -1) if nd["id"] in linked else -1

    # ---- discovery-order markers (browsing only)
    ew = findings.get("early_warning", {})
    rep = ew.get("replay", {})
    markers = [dict(sig=s, pos=v["pos"], frac=v["frac"])
               for s, v in (rep.get("per_signal_first_fire") or {}).items()]

    # ---- real clock: signal first-fires (strict run), milestones, hourly counts
    tc = ew.get("timestamp_crosscheck", {})
    clock_signals = [dict(sig=s, ts=v["ts"], prec=v.get("precision"))
                     for s, v in (tc.get("signals") or {}).items() if v.get("ts")]
    ms = getattr(log, "milestones", {}) or {}
    ms_labels = dict(_MILESTONE_LABELS, **(getattr(log, "milestone_labels", {}) or {}))
    short = getattr(log, "milestone_short", {}) or {}
    milestones = [dict(name=k, label=ms_labels.get(k, k), short=short.get(k, k), ts=v)
                  for k, v in sorted(ms.items(), key=lambda x: x[1])]

    timed = log.timed_events(include_inferred=True)
    hours_obs: Counter = Counter()
    hours_inf: Counter = Counter()
    for e in timed:
        h = int(e.ts // 3600)
        (hours_inf if e.ts_source == "inferred" else hours_obs)[h] += 1
    tmin = timed[0].ts if timed else None
    tmax = timed[-1].ts if timed else None
    # Default view window: the incident week if milestones exist, else the
    # middle 96% of dated events (a few outliers would squash everything).
    if ms:
        win = (min(ms.values()) - 2 * 86400, ms.get("hf_cut_access", max(ms.values())) + 86400)
        win = (max(win[0], tmin or win[0]), min(win[1], tmax or win[1]))
    elif timed:
        k = len(timed)
        win = (timed[int(0.02 * k)].ts, timed[int(0.98 * k) - 1].ts)
    else:
        win = None
    h0 = int(tmin // 3600) if tmin else 0
    h1 = int(tmax // 3600) if tmax else 0
    hourly = dict(start_hour=h0,
                  obs=[hours_obs.get(h, 0) for h in range(h0, h1 + 1)] if timed else [],
                  inf=[hours_inf.get(h, 0) for h in range(h0, h1 + 1)] if timed else [])

    # ---- discovery-order density (share of board / mailbox writes per slice)
    ordered = log.sorted_events(prefer_time)
    bins = 240
    n = max(1, len(ordered))
    dens_all, dens_coord = [0] * bins, [0] * bins
    for i, e in enumerate(ordered):
        b = min(bins - 1, i * bins // n)
        dens_all[b] += 1
        if e.has("board_token") or e.has("mailbox"):
            dens_coord[b] += 1

    inf = findings.get("inference", {})
    headline = dict(
        first_alert_when=tc.get("first_alert_when"),
        n_timed=tc.get("n_timed"),
        lead_private=(tc.get("lead_hours_by_signal") or {}).get("private_channel"),
        lead_board=(tc.get("lead_hours_by_signal") or {}).get("board"),
        attr_precision=(inf.get("attribution_eval", {}).get("all", {}) or {}).get("precision"),
        date_within_24h=inf.get("dating_eval", {}).get("within_24h"),
    )
    if attributed:
        A = findings["attributed"]
        sc = (A.get("changepoint") or {}).get("score") or {}
        claim = next((c for r in (A.get("authority") or {}).values() for c in r["claimants"]
                      if not c["assigned"]), None)
        rc = ((A.get("diffusion") or {}).get("case_studies") or {}).get("role_mentions", {}).get("vs_control")
        timed_ = log.timed_events()
        days_ = (timed_[-1].ts - timed_[0].ts) / 86400 if timed_ else 0
        headline = dict(attributed=True, first_alert_when=tc.get("first_alert_when"),
                        cp_alerts=len((A.get("changepoint") or {}).get("alerts") or []), days=round(days_, 1),
                        ms_source=getattr(log, "milestone_source", None),
                        daily_flagged=((A.get("changepoint") or {}).get("daily") or {}).get("flagged"),
                        daily_precision=((A.get("changepoint") or {}).get("daily") or {}).get("precision"),
                        drift_statements=((A.get("actions") or {}).get("role_drift") or {}).get("statements"),
                        cp_detected=sc.get("detected"), cp_total=sc.get("total"),
                        cp_false=sc.get("false_alerts"),
                        cp_rows=[(r["label"][10:50], r["detected"], r["delay_minutes"]) for r in sc.get("milestones", [])],
                        claim=claim and dict(agent=claim["agent"], endorsers=claim["endorsers"], ts=claim["first_claim"]),
                        role_before=rc and rc["before"]["share"], role_after=rc and rc["after"]["share"],
                        drift_alert=((A.get("actions") or {}).get("role_drift") or {}).get("alert"))
    forensics = _forensics(log, findings) if attributed else None
    cascades = _cascades(findings)
    s = findings.get("summary", {})
    return dict(
        meta=dict(source=log.name, village=getattr(log, "village", None), priv_role=priv_role, axis=act.axis, n_events=len(log), attributed=attributed,
                  n_agents=len(log.actors()), maxpos=maxpos, prefer_time=prefer_time,
                  named_total_frac=s.get("named_total_frac"), dated_total_frac=s.get("dated_total_frac")),
        clock=dict(tmin=tmin, tmax=tmax, window=win, n_timed=len(timed)),
        nodes=nodes, links=links, proj_links=proj_links,
        markers=markers, alert=rep.get("combined_first_alert"),
        clock_signals=clock_signals, milestones=milestones, hourly=hourly,
        density=dict(all=dens_all, coord=dens_coord),
        headline=headline,
        covert=findings.get("covert", {}).get("inventory", []),
        summary=s,
        forensics=forensics,
        cascades=cascades,
        exchanges=_exchanges(log, attributed, prefer_time),
    )


D3_CDN = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"


def write_html(graph_data: dict, out_html: str, title: str = "SwarmScope",
               mode: str = "local", template: str = "template.html") -> str:
    """Write the viewer.

    mode="local"    -> a full standalone document with D3 inlined; opens offline
                       by double-clicking the file.
    mode="artifact" -> page body only, D3 loaded from cdnjs; for publishing as a
                       hosted page (the host adds the document skeleton).
    template        -> "template.html" (graph viewer) or "world.html" (world map).
    """
    with open(os.path.join(_HERE, template)) as f:
        tpl = f.read()
    # "<\/" keeps text from the log (e.g. "</script>") from closing the data script.
    data = json.dumps(graph_data).replace("</", "<\\/")
    tpl = tpl.replace("/*__DATA__*/", data).replace("__TITLE__", html_escape(title))
    if mode == "artifact":
        html = tpl.replace("<script>/*__D3__*/</script>", f'<script src="{D3_CDN}"></script>')
    else:
        with open(os.path.join(_HERE, "d3.min.js")) as f:
            d3js = f.read()
        html = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                + tpl.replace("/*__D3__*/", d3js) + "\n</html>\n")
    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    with open(out_html, "w") as f:
        f.write(html)
    return out_html
