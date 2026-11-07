"""Run every detector and write the findings, the markdown report, and the viz.

``analyze`` returns one big JSON-serializable dict. ``write_outputs`` turns it
into ``findings.json``, a human-readable ``report.md``, and a self-contained
dynamic-graph HTML file.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Dict

from .events import EventLog
from .detectors import coordination, info_spread, covert, early_warning
from .viz import export


def _summary(log: EventLog, cov: dict, ew: dict, coord: dict) -> dict:
    kinds = Counter(e.kind for e in log.events)
    mech_rows = cov.get("inventory", [])
    alert = ew.get("replay", {}).get("combined_first_alert")
    return dict(
        source=log.name,
        n_events=len(log),
        kinds=dict(kinds),
        n_named_agents=len(log.actors()),
        axis=log.time_axis(),
        n_shared_deaddrops=len(coord.get("shared_deaddrops", [])),
        n_communities=coord.get("communities", {}).get("n_communities", 0),
        top_mechanisms=[(r["mechanism"], r["n_events"]) for r in mech_rows[:8]],
        combined_first_alert=alert,
    )


def analyze(log: EventLog, prefer_time: bool = True) -> dict:
    coord = coordination.run_all(log, prefer_time)
    spread = info_spread.run_all(log, prefer_time)
    cov = covert.run_all(log, prefer_time)
    ew = early_warning.run_all(log, prefer_time)
    summary = _summary(log, cov, ew, coord)
    return dict(summary=summary, coordination=coord, info_spread=spread,
                covert=cov, early_warning=ew)


# --------------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------------
def _md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def to_markdown(log: EventLog, f: dict) -> str:
    s = f["summary"]
    L = []
    L.append(f"# SwarmScope findings -- `{s['source']}`\n")
    L.append(f"- Events: **{s['n_events']:,}**  ({', '.join(f'{k}: {v:,}' for k,v in s['kinds'].items())})")
    L.append(f"- Named agents (signed their work): **{s['n_named_agents']:,}**")
    axis_note = {
        "estimated": "estimated order -- records sorted by when the resources they reference first appeared; a rough proxy for time, not a clock",
        "time": "real timestamps",
        "sequence": "raw log order",
    }.get(s["axis"], s["axis"])
    comm = f["coordination"]["communities"]
    L.append(f"- Time axis used: **{s['axis']}** ({axis_note})")
    L.append(f"- Shared dead-drops (resources used by >=2 named agents): **{s['n_shared_deaddrops']}**")
    L.append(f"- Agent communities with 2+ members: **{comm.get('n_nontrivial', 0)}** "
             f"({comm.get('n_isolated', 0)} named agents share nothing with another named agent)\n")

    # ---- who talked to whom
    L.append("## 1. Who talked to whom (reconstruction)\n")
    L.append("Agents in this log are de-identified, so coordination is reconstructed "
             "through **shared resources** -- a dataset, repo, or mailbox that two "
             "agents both used is an interaction through a dead-drop.\n")
    dd = f["coordination"]["shared_deaddrops"][:14]
    if dd:
        L.append("**Most-shared dead-drops** (`task_api` = share that is ordinary task-submission "
                 "traffic; `coord` = share that is board/mailbox writes):\n")
        L.append(_md_table(["resource", "agents", "events", "task_api", "coord"],
                           [(d["resource"], d["n_agents"], d["n_events"], d["task_api"], d["coord_use"]) for d in dd]))
        L.append("")
    dy = f["coordination"]["repeated_dyads"][:12]
    if dy:
        L.append("**Agent pairs sharing the most *telling* resources** (ranked by "
                 "Adamic-Adar, which discounts resources everyone uses; `shared` = raw count):\n")
        L.append(_md_table(["from", "to", "AA score", "shared"],
                           [(d["src"], d["dst"], d["score"], d["shared"]) for d in dy]))
        L.append("")
    al_g = f["coordination"].get("alias_groups", [])[:8]
    if al_g:
        L.append("**Probable aliases** (handles with the same stem, likely one agent "
                 "renaming itself after a restart -- a hint, not proof):\n")
        L.append(_md_table(["stem", "handles", "events"],
                           [(a["stem"], ", ".join(a["handles"][:6]), a["n_events"]) for a in al_g]))
        L.append("")
    dc = f["coordination"]["duplicate_control"]
    L.append(f"**Swarm self-management (locks / killing rivals):** {dc['n_events']} events. "
             f"Top controllers: {', '.join(f'{a} ({n})' for a,n in dc['top_controllers'][:6]) or 'none named'}.\n")

    # ---- info spread
    L.append("## 2. How information spread\n")
    L.append("We track specific items -- harvested credentials (the swarm's \"LOOT\") "
             "and dataset dead-drops -- and reconstruct who touched each one, in order.\n")
    for ref_type in ("credential", "destination"):
        block = f["info_spread"].get(ref_type, {})
        for tr in block.get("traces", [])[:2]:
            L.append(f"- **{tr['item']}** touched by {tr['n_touches']} events, "
                     f"{tr['n_distinct_actors']} named agents, over {tr['axis_span']} "
                     f"steps of the axis (velocity {tr['velocity']}).")
    L.append("")

    # ---- covert channels
    L.append("## 3. Covert channels used\n")
    inv = f["covert"]["inventory"]
    L.append(_md_table(["mechanism", "events", "share", "first seen (pos)", "what it is"],
                       [(r["mechanism"], f"{r['n_events']:,}", r["share"],
                         r["first_pos"], r["description"]) for r in inv]))
    cd = f["covert"]["chain_depth"]
    L.append(f"\nDecode / link chains reach depth **{cd['max_depth']}**; "
             f"**{cd['n_with_parent']:,}** records are a decoded layer of another record.\n")

    # ---- early warning
    L.append("## 4. Could it have flagged the coordination early?\n")
    rep = f["early_warning"]["replay"]
    rows = []
    for sig, v in rep.get("per_signal_first_fire", {}).items():
        rows.append((sig, v["pos"], f"{v['frac']*100:.1f}%"))
    rows.sort(key=lambda x: x[1])
    L.append("We replay the log in order and use only what was visible so far "
             "(an online detector). Two views:\n")
    L.append("**(a) Estimated-order replay** -- all events, first firing as a fraction of the stream:\n")
    L.append(_md_table(["signal", "first pos", "fraction of stream"], rows))
    al = rep.get("combined_first_alert")
    if al:
        L.append(f"\nCombined multi-agent alert at **{al['frac']*100:.2f}%** of the stream "
                 f"(rule: {al['rule']}); **{al['activity_still_ahead_frac']*100:.1f}%** of recorded "
                 f"activity comes after it. Read this with care: the order is estimated, so this says "
                 f"the board shows up among the *first* things reconstructed, not an exact clock time.\n")
    tc = f["early_warning"]["timestamp_crosscheck"]
    if tc.get("axis") == "time":
        L.append(f"**(b) Real-time replay** -- only the {tc['n_timed']:,} events with a trusted "
                 f"date inside the incident window:\n")
        srows = sorted(((k, v["when"]) for k, v in tc.get("signals", {}).items()),
                       key=lambda x: x[1] or "")
        L.append(_md_table(["signal", "first fires (UTC)"], srows))
        if tc.get("first_alert_when"):
            L.append(f"\nFirst multi-agent alert on the real clock: **{tc['first_alert_when']}**. "
                     f"{tc.get('dated_activity_after_alert_frac', 0)*100:.1f}% of dated activity came after it.\n")
        lh = tc.get("lead_hours") or {}
        if lh:
            L.append("Lead time from that alert to each known milestone "
                     "(milestones from the METR/Redwood and Swarm Traces reports; negative = milestone came first):\n")
            L.append(_md_table(["milestone", "hours after alert"],
                               [(k, v) for k, v in lh.items()]))
            L.append("")
        per = tc.get("lead_hours_by_signal") or {}
        if per:
            L.append("Hours of warning each signal alone would have given "
                     "(`board` relies on knowing the swarm's message format; "
                     "`private_channel` uses structure only):\n")
            L.append(_md_table(["signal", "before HF creds found", "before HF worker RCE", "before public discovery"],
                               [(s, v.get("hf_credentials_found"), v.get("hf_worker_rce"), v.get("public_discovery"))
                                for s, v in sorted(per.items(), key=lambda x: -(x[1].get("hf_worker_rce") or 0))]))
            L.append("\n_How to read this:_ `credential_reuse` and `signed_cmd` fire months early but are "
                     "**not specific** -- one agent can reuse its own key, and the signature check is a keyword "
                     "match -- so alone they would mostly raise false alarms. The useful signals are the "
                     "multi-agent ones (`board`, `private_channel`). Dates with no time of day are read as "
                     "00:00 UTC, so the `board` time is accurate only to the day (its lead could be up to ~24 h "
                     "shorter). We have no benign *real* control log yet, so real-world false-alarm rates are "
                     "**not measured**; that is the main job of the AI Village run. On synthetic logs with a "
                     "planted colluding pair (`tests/test_synthetic.py`, 100 seeds) `private_channel` has "
                     "100% recall, 0% early fires and 0% false alarms -- an easy test, so treat it as a sanity check.\n")
    else:
        L.append(f"_Real-time replay: {tc.get('note','n/a')}._\n")

    # ---- blind spots
    L.append("## 5. What an investigator would still miss\n")
    L.append(_blind_spots(log, f))
    return "\n".join(L)


def _blind_spots(log: EventLog, f: dict) -> str:
    n = len(log)
    no_ts = sum(1 for e in log.events if e.ts is None)
    unattributed = sum(1 for e in log.events if not e.actor)
    pts = [
        f"**Identity is redacted.** The `agent_id` field is masked, so {unattributed/n*100:.0f}% "
        "of events have no provable author. We attribute an actor only when an agent *signed* its "
        "work on the board. Real coordination between unsigned agents is invisible to the graph.",
        "**Names are self-chosen and plentiful.** The source report extracted ~7,905 unique names "
        "for ~700 attacking agents, so one agent may wear many handles and the agent count cannot be trusted.",
        f"**Time is mostly unknown.** {no_ts/n*100:.1f}% of events carry no trusted timestamp. The main "
        "axis is an *estimated* order (first appearance of referenced resources), which only roughly "
        "tracks real time. The real-clock replay uses the small dated subset, which may not be "
        "representative of the whole swarm.",
        "**The capture is one-sided.** ~80% of the data is outbound payloads; the responses that would "
        "confirm what actually executed are largely missing, and later traffic was encrypted.",
        "**Encrypted / deleted content is opaque.** Signed and encrypted commands, deleted webhooks, and "
        "short-lived pastes mean the tool sees that a channel existed, not what passed through it.",
        "**Intent is not in the data.** The graph shows structure (who shared what, when); it cannot tell "
        "coordinated attack from parallel coincidence. Every alert here is a lead for a human, not a verdict.",
        "**Dead-drops hide direction.** When two agents use the same dataset we infer write-then-read from "
        "order, but we cannot prove either read the other's bytes, so some edges are over- or under-stated.",
    ]
    return "\n\n".join(f"- {p}" for p in pts)


def write_outputs(log: EventLog, findings: dict, out_dir: str,
                  prefer_time: bool = True, title: str = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    fj = os.path.join(out_dir, "findings.json")
    with open(fj, "w") as fp:
        json.dump(findings, fp, indent=2, default=str)
    md = os.path.join(out_dir, "report.md")
    with open(md, "w") as fp:
        fp.write(to_markdown(log, findings))
    gd = export.build_graph_data(log, findings, prefer_time)
    html = os.path.join(out_dir, f"swarmscope_{log.name}.html")
    export.write_html(gd, html, title=title or f"SwarmScope {log.name.replace('_', ' ').title()}")
    return dict(findings=fj, report=md, html=html)
