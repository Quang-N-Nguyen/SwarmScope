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
import os
from collections import Counter, defaultdict
from typing import Dict, Optional

from ..events import EventLog
from ..graph import build_activity_graph, build_agent_projection

_HERE = os.path.dirname(__file__)

_MILESTONE_LABELS = {
    "main_board_established": "Main board set up (METR)",
    "hf_credentials_found": "HF credentials found",
    "hf_file_read": "HF arbitrary file read",
    "hf_worker_rce": "RCE on HF worker",
    "coordinators_stopped": "Coordinators stopped",
    "hf_cut_access": "HF cut access",
    "public_discovery": "Public discovery",
}


def _utc(ts):
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc)


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

    # ---- nodes
    nodes = []
    for nid, n in act.nodes.items():
        comm = comms.get(nid)
        lab = n["label"]
        r = roles.get(lab, {}) if n["type"] == "agent" else {}
        ld = leaders.get(lab, {})
        nodes.append(dict(
            id=nid, ty=n["type"], lab=lab, c=n["count"],
            p0=n["first_pos"], pn=n["last_pos"], t0=n["first_ts"], tn=n["last_ts"],
            comm=(comm if comm is not None else -1),
            mech=[m for m, _ in n["features"].most_common(3)],
            obs=n.get("obs"), inf=n.get("inf"),
            role=r.get("role"), spec=r.get("specialisation"), tac=r.get("tactics"),
            led=ld.get("led"), fol=ld.get("followed"), betw=brokers.get(lab)))

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

    # ---- agent-agent edges (observed authors only)
    proj_links = [dict(s=e["src"], t=e["dst"], p0=e["pos"], t0=e.get("ts"),
                       w=e.get("weight", 1)) for e in proj.edges]

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
    milestones = [dict(name=k, label=_MILESTONE_LABELS.get(k, k), ts=v) for k, v in sorted(ms.items(), key=lambda x: x[1])]

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
    s = findings.get("summary", {})
    return dict(
        meta=dict(source=log.name, axis=act.axis, n_events=len(log),
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
    )


D3_CDN = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"


def write_html(graph_data: dict, out_html: str, title: str = "SwarmScope",
               mode: str = "local") -> str:
    """Write the viewer.

    mode="local"    -> a full standalone document with D3 inlined; opens offline
                       by double-clicking the file.
    mode="artifact" -> page body only, D3 loaded from cdnjs; for publishing as a
                       hosted page (the host adds the document skeleton).
    """
    with open(os.path.join(_HERE, "template.html")) as f:
        tpl = f.read()
    tpl = tpl.replace("/*__DATA__*/", json.dumps(graph_data)).replace("__TITLE__", title)
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
