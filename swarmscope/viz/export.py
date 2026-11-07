"""Shape graph + detector output into the JSON the HTML viewer reads, and
assemble a single self-contained HTML file (D3 is inlined, so it opens offline).
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Dict, Optional

from ..events import EventLog
from ..graph import build_activity_graph, build_agent_projection

_HERE = os.path.dirname(__file__)


def build_graph_data(log: EventLog, findings: Optional[dict] = None,
                     prefer_time: bool = True, top_resources: int = 120) -> dict:
    act = build_activity_graph(log, prefer_time, top_resources=top_resources)
    proj, comms = build_agent_projection(log, prefer_time)

    maxpos = 0
    for n in act.nodes.values():
        maxpos = max(maxpos, n["last_pos"])
    maxpos = max(maxpos, 1)

    # nodes (activity graph carries agents + resources; attach community)
    nodes = []
    for nid, n in act.nodes.items():
        comm = comms.get(nid)
        mech = [m for m, _ in n["features"].most_common(3)]
        nodes.append(dict(id=nid, ty=n["type"], lab=n["label"], c=n["count"],
                          p0=n["first_pos"], pn=n["last_pos"],
                          comm=(comm if comm is not None else -1), mech=mech))

    # aggregate activity edges by (src,dst,kind) -> first/last pos + count
    agg: Dict[tuple, dict] = {}
    for e in act.edges:
        key = (e["src"], e["dst"], e["kind"])
        a = agg.get(key)
        if a is None:
            agg[key] = dict(s=e["src"], t=e["dst"], k=e["kind"],
                            p0=e["pos"], pn=e["pos"], w=1)
        else:
            a["p0"] = min(a["p0"], e["pos"]); a["pn"] = max(a["pn"], e["pos"]); a["w"] += 1
    links = list(agg.values())

    # projection edges
    proj_links = []
    for e in proj.edges:
        proj_links.append(dict(s=e["src"], t=e["dst"], p0=e["pos"],
                               w=e.get("weight", 1)))

    # early-warning markers for the timeline
    markers = []
    ew = (findings or {}).get("early_warning", {}).get("replay", {})
    for sig, v in (ew.get("per_signal_first_fire") or {}).items():
        markers.append(dict(sig=sig, pos=v["pos"], frac=v["frac"]))
    alert = ew.get("combined_first_alert")

    covert_inv = (findings or {}).get("covert", {}).get("inventory", [])

    # Activity density along the axis, for the timeline strip: all events, and
    # the board / mailbox subset (where coordination is visible).
    ordered = log.sorted_events(prefer_time)
    bins = 240
    n = max(1, len(ordered))
    dens_all = [0] * bins
    dens_coord = [0] * bins
    for i, e in enumerate(ordered):
        b = min(bins - 1, i * bins // n)
        dens_all[b] += 1
        if e.has("board_token") or e.has("mailbox"):
            dens_coord[b] += 1

    # Headline numbers for the sidebar (real-clock replay, if any).
    tc = (findings or {}).get("early_warning", {}).get("timestamp_crosscheck", {})
    headline = dict(
        first_alert_when=tc.get("first_alert_when"),
        n_timed=tc.get("n_timed"),
        lead_private=(tc.get("lead_hours_by_signal") or {}).get("private_channel"),
        lead_board=(tc.get("lead_hours_by_signal") or {}).get("board"),
    )

    return dict(
        density=dict(all=dens_all, coord=dens_coord),
        headline=headline,
        meta=dict(source=log.name, axis=act.axis, n_events=len(log),
                  n_agents=len(log.actors()), maxpos=maxpos,
                  prefer_time=prefer_time),
        nodes=nodes, links=links, proj_links=proj_links,
        markers=markers, alert=alert,
        covert=covert_inv,
        summary=(findings or {}).get("summary", {}),
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
