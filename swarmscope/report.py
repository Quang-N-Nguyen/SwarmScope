"""Run inference + every detector, then write findings, report, and viewer.

``analyze`` returns one JSON-serializable dict. ``write_outputs`` turns it into
``findings.json``, a readable ``report.md``, and a self-contained viewer HTML.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from collections import Counter
from typing import Dict

from .events import EventLog
from .detectors import coordination, info_spread, covert, early_warning, research
from .graph import build_agent_projection
from .infer import links as links_mod, attribution, dating, aliases
from .viz import export

# Inference presets: how far to stretch the evidence. Numbers from the
# held-out sweep on Swarm Traces (scripts/sweep_inference.py, Nov 2026):
#   precise : names 1.3% of events at 0.95 precision; dates 4.7% (97% within 24 h)
#   balanced: names 1.3% at 0.95 precision; dates 10.6% (94% within 24 h)
#   broad   : names 6.5% at 0.83 precision; dates 15.8% (93% within 24 h)
PRESETS = {
    "precise":  dict(attr_T=10, attr=dict(rounds=3, min_share=0.8, min_weight=0.4),
                     date_T=10, date=dict(hops=2)),
    "balanced": dict(attr_T=10, attr=dict(rounds=3, min_share=0.8, min_weight=0.4),
                     date_T=25, date=dict(hops=4)),
    "broad":    dict(attr_T=25, attr=dict(rounds=6, min_share=0.8, min_weight=0.3),
                     date_T=50, date=dict(hops=4)),
}


def _fmt_ts(ts):
    if ts is None:
        return "-"
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def infer(log: EventLog, preset: str = "balanced") -> dict:
    """Fill authors, dates and alias candidates. Returns the evaluations."""
    if preset == "off":
        return dict(preset="off")
    p = PRESETS[preset]
    has_fp = any(e.fingerprints for e in log.events[:5000]) or any(e.refs for e in log.events[:5000])
    if not has_fp:
        return dict(preset=preset, note="no identifiers to link on")
    La = links_mod.build(log, max_events=p["attr_T"])
    out = dict(preset=preset, settings=p, link_edges_attribution=La.n_edges)
    out["attribution_eval"] = attribution.evaluate(log, La, **p["attr"])
    out["attribution"] = attribution.run(log, La, **p["attr"])
    Ld = La if p["date_T"] == p["attr_T"] else links_mod.build(log, max_events=p["date_T"])
    out["dating_eval"] = dating.evaluate(log, Ld, **p["date"])
    if any(e.order_hint is not None for e in log.events):
        out["token_order_eval"] = dating.evaluate_token_order(log, Ld)
    out["dating"] = dating.run(log, Ld, **p["date"])
    out["aliases"] = aliases.run(log)
    return out


def _summary(log: EventLog, cov: dict, coord: dict, inf: dict, res: dict) -> dict:
    kinds = Counter(e.kind for e in log.events)
    a = inf.get("attribution", {})
    d = inf.get("dating", {})
    return dict(
        source=log.name,
        n_events=len(log),
        kinds=dict(kinds),
        n_named_agents=len(log.actors()),
        axis=log.time_axis(),
        named_observed_frac=a.get("named_observed_frac"),
        named_total_frac=a.get("named_total_frac"),
        events_in_personas_frac=a.get("events_in_personas_frac"),
        dated_observed_frac=d.get("dated_observed_frac"),
        dated_total_frac=d.get("dated_total_frac"),
        n_shared_deaddrops=len(coord.get("shared_deaddrops", [])),
        n_validated_ties=res.get("validated_ties", {}).get("validated"),
        top_mechanisms=[(r["mechanism"], r["n_events"]) for r in cov.get("inventory", [])[:8]],
    )


def analyze(log: EventLog, prefer_time: bool = True, inference: str = "balanced") -> dict:
    inf = infer(log, inference)
    coord = coordination.run_all(log, prefer_time)
    spread = info_spread.run_all(log, prefer_time)
    cov = covert.run_all(log, prefer_time)
    ew = early_warning.run_all(log, prefer_time)
    proj, comms = build_agent_projection(log, prefer_time)
    strong = [dict(a=e["src"].split(":", 1)[1], b=e["dst"].split(":", 1)[1], score=e.get("weight", 0))
              for e in proj.edges if e.get("weight", 0) >= 1.0]
    res = research.run_all(log, comms, strong)
    summary = _summary(log, cov, coord, inf, res)
    return dict(summary=summary, inference=inf, coordination=coord, info_spread=spread,
                covert=cov, early_warning=ew, research=res)


# --------------------------------------------------------------------------
# Markdown report
# --------------------------------------------------------------------------
def _md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _pct(x):
    return "-" if x is None else f"{x*100:.1f}%"


def to_markdown(log: EventLog, f: dict) -> str:
    s, inf, res = f["summary"], f.get("inference", {}), f.get("research", {})
    L = []
    L.append(f"# SwarmScope findings: `{s['source']}`\n")
    L.append(f"- Events: **{s['n_events']:,}** ({', '.join(f'{k}: {v:,}' for k, v in s['kinds'].items())})")
    L.append(f"- Named agents (signed a board token): **{s['n_named_agents']:,}**")
    if s.get("named_total_frac") is not None:
        L.append(f"- Events with a named author: **{_pct(s['named_observed_frac'])}** observed, "
                 f"**{_pct(s['named_total_frac'])}** with inferred names; "
                 f"**{_pct(s['events_in_personas_frac'])}** grouped into probable-same-author personas")
        L.append(f"- Events with a real-clock time: **{_pct(s['dated_observed_frac'])}** read from the data, "
                 f"**{_pct(s['dated_total_frac'])}** with inferred times")
    L.append(f"- Shared dead-drops (2+ named agents): **{s['n_shared_deaddrops']}**; "
             f"statistically validated agent ties (signed events only): **{s.get('n_validated_ties')}**")
    L.append(f"- Inference preset: **{inf.get('preset', 'off')}**. Main browsing axis: **{s['axis']}** "
             f"(discovery order, which is not a clock; all time claims below use real dates)\n")

    # ---- 1. who talked to whom
    L.append("## 1. Who talked to whom\n")
    L.append("Agent names are redacted, so we reconstruct interaction through **shared resources**. "
             "A dataset, repository, mailbox or credential that two agents both used is an interaction "
             "through a dead-drop.\n")
    dd = f["coordination"]["shared_deaddrops"][:12]
    if dd:
        L.append("**Most-shared dead-drops** (`task_api` = share of events that are ordinary task-submission "
                 "calls; `coord` = share that are board / mailbox writes):\n")
        L.append(_md_table(["resource", "agents", "events", "task_api", "coord"],
                           [(d["resource"], d["n_agents"], d["n_events"], d["task_api"], d["coord_use"]) for d in dd]))
        L.append("")
    vt = res.get("validated_ties", {})
    if vt:
        L.append(f"**Statistically validated ties** (Tumminello et al., 2011; null model after Neal, 2014). "
                 f"Of {vt['pairs_tested']:,} possible pairs among {vt['agents']} agents, "
                 f"{vt['pairs_sharing_any']:,} share at least one resource, but only **{vt['validated']}** share "
                 f"more than chance allows once resource popularity is taken into account (Poisson-binomial "
                 f"test, Benjamini-Hochberg FDR {vt['alpha']}). {vt['resources_dropped_as_task_api']} task-API "
                 f"resources were left out first. The test is cautious: on synthetic data it never produced "
                 f"a false tie, but it needs a pair to share about 8 rare resources before it is sure.\n")
        if vt["ties"]:
            L.append(_md_table(["agent A", "agent B", "shared resources", "p-value"],
                               [(t["a"], t["b"], t["shared"], t["p"]) for t in vt["ties"][:12]]))
            L.append("")
        else:
            L.append(f"Why none: each signed agent uses only about {vt['median_resources_per_agent']} resources "
                     f"(median), so the best pair reaches p = {vt['min_p']}, while the bar for the best of "
                     f"{vt['pairs_tested']:,} pairs is {vt['bar_for_best_pair']}. This is a **power** problem "
                     f"caused by sparse attribution, not proof that no pair colluded. Closest pairs:\n")
            L.append(_md_table(["agent A", "agent B", "shared resources", "p-value"],
                               [(t["a"], t["b"], t["shared"], t["p"]) for t in vt.get("best_pairs", [])]))
            vi = res.get("validated_ties_with_inferred", {})
            if vi:
                L.append(f"\nWith inferred authors the test validates {vi['validated']:,} ties, but we do not "
                         f"report that as a finding: inference and the test use the same identifiers, so the "
                         f"number is inflated by construction.\n")
        L.append(f"Brokers and the audit budget below use the **{res.get('tie_set_for_structure')}** tie set "
                 f"({res.get('n_structure_ties', 0):,} ties).\n")
    dc = f["coordination"]["duplicate_control"]
    L.append(f"**Swarm self-management** (elections, locks, killing rival controllers): {dc['n_events']} events "
             f"with a board token. Top named controllers: "
             f"{', '.join(f'{a} ({n})' for a, n in dc['top_controllers'][:6]) or 'none named'}.\n")

    # ---- 2. information spread
    L.append("## 2. How information spread\n")
    cas = res.get("cascades", [])
    if cas:
        L.append("Each row is one item (a credential or a dead-drop dataset), on the real clock "
                 "(read and inferred dates). `hours to half` = time until half of the agents that ever "
                 "used it had used it.\n")
        L.append(_md_table(["item", "first agent", "agents reached", "span (h)", "hours to half", "communities"],
                           [(c["item"], c["origin"], c["agents"], c["span_hours"], c["hours_to_half"], c["communities"])
                            for c in cas]))
        L.append("")
    bf = res.get("board_file_spread", {})
    if bf:
        L.append(f"**Shared board files.** {bf['files']} files were posted on the board (`zzFILE_*`). "
                 f"{bf['files_used_by_other_agents']} of them also appear in events by *other* named agents "
                 f"(a lower bound, because a reader is often labelled with the file's publisher).\n")
        rows = [(r["file"][:40], r["publisher"], r["events"], r["other_agents"], ", ".join(r["others"][:4]))
                for r in bf["top"][:8] if r["other_agents"]]
        if rows:
            L.append(_md_table(["file", "publisher", "events", "other agents", "examples"], rows))
            L.append("")

    # ---- 3. covert channels
    L.append("## 3. Covert channels and tactics\n")
    tac = research.TACTICS
    inv = f["covert"]["inventory"]
    L.append(_md_table(["mechanism", "events", "ATT&CK", "what it is"],
                       [(r["mechanism"], f"{r['n_events']:,}",
                         (f"{tac[r['mechanism']][1]} {tac[r['mechanism']][2]}" if r["mechanism"] in tac else "baseline"),
                         r["description"]) for r in inv]))
    cd = f["covert"]["chain_depth"]
    L.append(f"\n{cd['n_with_parent']:,} records are a decoded layer or response of another record "
             f"(maximum chain depth {cd['max_depth']}).\n")
    L.append("_Code review note (Nov 2026):_ the first version used very broad keywords (for example "
             "\"elect\" matched `querySelector`), so it over-counted some mechanisms by up to 15 times. "
             "The patterns are now specific; see `swarmscope/extract.py`.\n")

    # ---- 4. early warning
    L.append("## 4. Could it have flagged the coordination early?\n")
    L.append("We replay the dated events in time order with an online detector: at each moment it uses "
             "only what it has seen so far. Two runs:\n")
    for key, label in (("timestamp_crosscheck", "Strict (only dates and names read from the data)"),
                       ("extended", "Extended (also inferred dates and names)")):
        tc = f["early_warning"].get(key, {})
        if tc.get("axis") != "time":
            continue
        L.append(f"**{label}**: {tc['n_timed']:,} dated events.\n")
        def _prec(v):
            p = v.get("precision")
            if p == "second" and v.get("ts") is not None and v["ts"] % 86400 == 0:
                return "second (exactly midnight: may be a date with no time)"
            return p
        srows = sorted(((k, v["when"], _prec(v)) for k, v in tc.get("signals", {}).items()),
                       key=lambda x: x[1] or "")
        L.append(_md_table(["signal", "first fires (UTC)", "date precision"], srows))
        per = tc.get("lead_hours_by_signal") or {}
        if per:
            L.append("\nHours of warning before each milestone (negative = the milestone came first):\n")
            L.append(_md_table(["signal", "before HF credentials found", "before HF worker RCE", "before public discovery"],
                               [(sg, v.get("hf_credentials_found"), v.get("hf_worker_rce"), v.get("public_discovery"))
                                for sg, v in sorted(per.items(), key=lambda x: -(x[1].get("hf_worker_rce") or -1e9))]))
        L.append("")
    L.append("_Strict vs extended:_ the extended run moves some signals weeks earlier. Those first firings "
             "rest on one or a few inferred dates, and the date test above shows a long error tail (90th "
             "percentile in hours, not days, but not zero). Treat an extended first firing as a lead to "
             "check, and the strict run as the result.\n")
    L.append("_How to read this:_ `credential_reuse` and `signed_cmd` fire months early but are not specific "
             "(one agent can reuse its own key), so alone they would raise many false alarms. The useful "
             "signals are the multi-agent ones: `private_channel` (structure only: a non-task resource used "
             "repeatedly by 2-3 agents) and `board` (needs the swarm's own message format, which an "
             "investigator learns only in hindsight). A date with no time of day is read as 12:00 UTC, so "
             "its error can be up to 12 hours. Milestones come from the METR/Redwood report. Real-world "
             "false-alarm rates are not measured yet; on synthetic logs with a planted colluding pair "
             "(`tests/test_synthetic.py`, 100 seeds) `private_channel` has 100% recall, 0% early fires and "
             "0% false alarms.\n")

    # ---- 5. fixing the blind spots
    L.append("## 5. Fixing the blind spots (with measured accuracy)\n")
    ae, ar = inf.get("attribution_eval", {}), inf.get("attribution", {})
    if ar:
        a_all, a_w = ae.get("all", {}), ae.get("write", {})
        L.append("**Who wrote it? (label propagation over rare shared identifiers)**\n")
        L.append(f"- Held-out test (whole decode chains hidden, 5 folds): precision **{a_all.get('precision')}** "
                 f"at coverage {a_all.get('coverage')} over {a_all.get('held_out')} signed events; "
                 f"on write events only, precision {a_w.get('precision')} at coverage {a_w.get('coverage')}.")
        L.append(f"- Result: named events go from **{ar['named_observed']:,}** ({_pct(ar['named_observed_frac'])}) "
                 f"to **{ar['named_observed'] + ar['named_inferred']:,}** ({_pct(ar['named_total_frac'])}).")
        L.append(f"- Personas (events joined by the same chain or an identifier used by at most 4 events): "
                 f"**{_pct(ar['events_in_personas_frac'])}** of events "
                 f"({_pct(ar.get('events_in_multi_payload_personas_frac'))} in personas that join 2+ different "
                 f"payloads, which is the part that adds real same-author information), B-cubed precision "
                 f"**{ar['persona_bcubed']['precision']}** (recall {ar['persona_bcubed']['recall']}). "
                 f"{ar['anonymous_personas']:,} personas have no name ({ar['anonymous_personas_ge5']:,} with 5+ events). "
                 f"{ar['n_personas_joining_several_handles']} personas contain 2+ different signed handles: "
                 f"either aliases or label noise.\n")
    de, dr = inf.get("dating_eval", {}), inf.get("dating", {})
    if dr:
        L.append("**When did it happen? (anchor propagation, weighted median of linked dated events)**\n")
        L.append(f"- Held-out test on {de.get('held_out')} clock-precise anchors: coverage {de.get('coverage')}, "
                 f"median error **{de.get('error_hours_median')} h**, 80th percentile {de.get('error_hours_p80')} h, "
                 f"90th percentile {de.get('error_hours_p90')} h, {_pct(de.get('within_24h'))} within 24 h. "
                 f"Baseline (always guess the median time): {de.get('baseline_median_day_error_hours')} h.")
        L.append(f"- Result: dated events go from **{dr['dated_observed']:,}** ({_pct(dr['dated_observed_frac'])}) "
                 f"to **{dr['dated_observed'] + dr['dated_inferred']:,}** ({_pct(dr['dated_total_frac'])}).")
        te = inf.get("token_order_eval", {})
        if te:
            rows = [(fam, v.get("n"), v.get("error_hours_median"), v.get("baseline_error_hours_median"),
                     "yes" if v.get("better_than_baseline") else "**no**") for fam, v in te.items()]
            L.append("- **Negative result:** the order of redaction numbers does not tell time. A monotone "
                     "fit from number to time is worse than always guessing the median:\n")
            L.append(_md_table(["token family", "anchors", "median error (h)", "baseline (h)", "better?"], rows))
        L.append("")
    al = inf.get("aliases", {})
    if al:
        L.append("**Which handles are one agent? (record linkage on personal identifiers)**\n")
        L.append(f"- {al['stem_pairs']} handle pairs share a name stem (for example URI23816C / URI23816D). "
                 f"{al['stem_pairs_sharing_personal_id']} of them share a personal identifier, against "
                 f"{_pct(al['random_pairs_sharing_personal_id_frac'])} of random pairs. AUC "
                 f"**{al['auc_stem_vs_random']}**: weak evidence.")
        L.append("- Many stems look like benchmark task names (LIBJXL3733, SKIA6295, GEOS33474), so a shared "
                 "stem may mean the same task, not the same agent.")
        if al.get("likely_aliases"):
            L.append("- Likely aliases (same stem and a shared personal identifier): " +
                     ", ".join(f"{x['a']}={x['b']}" for x in al["likely_aliases"][:12]) + ".")
        L.append("")

    # ---- 6. researcher view
    L.append("## 6. Researcher view\n")
    t = res.get("tactics", {})
    if t:
        need = t["min_agents_to_cover_all"]
        L.append(f"**Tactics (MITRE ATT&CK) and patchwork capability** (Tomasev et al., 2025). The named "
                 f"agents together cover **{t['group_tactics']}** tactic groups; the most versatile single agent "
                 f"covers **{t['best_single_agent_tactics']}**; a greedy set cover needs **{need}** "
                 f"agent{'s' if need != 1 else ''} to cover them all. Mean specialisation "
                 f"{t['mean_specialisation']} (1 = one tactic only). Caution: an event that mentions another "
                 f"agent's board file is credited to that agent, which can make one agent look more versatile "
                 f"than it was.\n")
        L.append(_md_table(["tactic", "techniques", "events", "agents"],
                           [(r["tactic"], "; ".join(r["techniques"]), f"{r['events']:,}", r["agents"]) for r in t["table"]]))
        L.append(f"\nRoles (each agent's main tactic, leaving out the board-token flag that every named "
                 f"agent has by construction): " +
                 ", ".join(f"{k} {v}" for k, v in t["role_counts"]) + ". Cover set: " +
                 ", ".join(t["cover_set"][:8]) + ".\n")
    ww = res.get("who_when", [])
    if ww:
        L.append("**Who and when** (Zhang et al., 2025): the first dated event for each tactic.\n")
        rows = []
        for r in ww:
            o, a = r["first_observed"], r["first_incl_inferred"]
            rows.append((r["tactic"], _fmt_ts(o["ts"]) if o else "-", o["who"] if o else "-",
                         _fmt_ts(a["ts"]) if a else "-", a["who"] if a else "-"))
        L.append(_md_table(["tactic", "first (read dates)", "who", "first (incl. inferred)", "who"], rows))
        L.append("")
    lb = res.get("leaders_brokers", {})
    if lb.get("leaders"):
        L.append("**Leaders and brokers.** A leader touches a shared resource first and others follow "
                 "(leader-follower structure, on the real clock). A broker sits between groups on the tie "
                 f"graph ({res.get('tie_set_for_structure')} ties; betweenness, Brandes, 2001). A very long "
                 "median lag (hundreds of hours) means the leader's first use was weeks before the others, "
                 "so it is weak evidence of leading.\n")
        L.append(_md_table(["leader", "followers led", "times followed", "median lag (h)"],
                           [(x["agent"], x["led"], x["followed"], x["median_lag_hours"]) for x in lb["leaders"][:8]]))
        if lb.get("brokers"):
            L.append("\n" + _md_table(["broker", "betweenness", "ties"],
                                      [(x["agent"], x["betweenness"], x["degree"]) for x in lb["brokers"][:8]]))
        L.append("")
    ab = res.get("audit_budget", {})
    if ab.get("agents_ranked"):
        need = ab.get("agents_needed", {})
        parts = [f"{k} of ties after {v[0]} agents ({_pct(v[1])} of agents)" for k, v in need.items()]
        L.append(f"**Audit budget** (Greenblatt et al., 2024). We rank agents by covert-mechanism events and "
                 f"audit from the top. Coverage of the {ab['ties']:,} {res.get('tie_set_for_structure')} ties: "
                 + "; ".join(parts) + ". The ties come from shared resources and the ranking from mechanism "
                 "flags, so this checks the ranking against an independent signal.\n")
    bu = res.get("bursts", {})
    if bu.get("bursts"):
        L.append("**Bursts** (hours far above the mean, real clock):\n")
        L.append(_md_table(["hour", "events", "z", "top mechanisms"],
                           [(b["hour"], b["events"], b["z"], ", ".join(f"{m} {n}" for m, n in b["top_mechanisms"]))
                            for b in bu["bursts"][:6]]))
        L.append("")

    # ---- 7. blind spots
    L.append("## 7. What an investigator would still miss\n")
    L.append(_blind_spots(log, f))
    L.append("\nFull method notes and all sources: `PROJECT_PLAN.md`.")
    return "\n".join(L)


def _blind_spots(log: EventLog, f: dict) -> str:
    n = len(log)
    inf = f.get("inference", {})
    ar, dr = inf.get("attribution", {}), inf.get("dating", {})
    named = ar.get("named_total_frac")
    dated = dr.get("dated_total_frac")
    pts = [
        f"**Most authors stay unknown.** Names are redacted at the source. Inference raises named events "
        f"to {_pct(named)} and groups {_pct(ar.get('events_in_personas_frac'))} of events into personas, "
        "but most personas are anonymous and many are one payload plus its decoded layers. Coordination "
        "between agents that never signed anything is still invisible.",
        f"**Most times stay unknown.** After inference, {_pct(dated)} of events have a time. The dated subset "
        "may not represent the swarm, and the order of redaction numbers is not a clock (tested above).",
        "**Aliases are only weakly resolved.** Agents name themselves (the source report found ~7,905 names "
        "for ~700 agents). Behavioural evidence separates same-stem pairs from random pairs only weakly.",
        "**The capture is one-sided.** About 80% of the data is outbound payloads. Responses that would "
        "confirm what actually ran are mostly missing.",
        "**Encrypted or deleted content is opaque.** We see that a signed or encrypted channel existed, not "
        "what it carried.",
        "**Intent is not in the data.** The graph shows structure, not purpose. Every alert is a lead for a "
        "human, not a verdict.",
        "**Dead-drops hide direction.** We infer write-then-read from time order. We cannot prove that one "
        "agent read another's bytes.",
        "**What would fix this at the source.** Deployers should log a stable agent ID and a timestamp on every "
        "outbound request, as proposed for agent infrastructure by Chan et al. (2025). Investigators with "
        "access to the unredacted data (header names, JWT and gzip times, which the Swarm Traces authors used) "
        "could re-run this tool with far less inference.",
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
