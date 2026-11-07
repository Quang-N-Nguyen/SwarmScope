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
from .detectors import conversation, diffusion, changepoint, authority, actions
from .detectors import rooms, emergence, influence
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


def is_attributed(log: EventLog) -> bool:
    """True when most events name their author (AI Village, most chat logs)."""
    return bool(log.events) and sum(1 for e in log.events if e.actor) >= 0.5 * len(log)


def analyze_attributed(log: EventLog) -> dict:
    """Detectors that need real names and clock times (see detectors/*.py)."""
    au = authority.run_all(log)
    return dict(conversation=conversation.run_all(log),
                diffusion=diffusion.run_all(log, getattr(log, "case_studies", None)),
                changepoint=changepoint.run_all(log),
                authority=au,
                actions=actions.run_all(log, au),
                rooms=rooms.run_all(log),
                emergence=emergence.run_all(log),
                influence=influence.run_all(log))


def analyze(log: EventLog, prefer_time: bool = True, inference: str = "balanced") -> dict:
    attributed = is_attributed(log)
    if attributed:
        # Names and times are in the data: nothing to infer.
        inf = dict(preset="off", note="authors and times are recorded in this log")
    else:
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
    summary["attributed"] = attributed
    if attributed:
        summary["n_ai_agents"] = len({e.actor for e in log.events if e.actor and not e.actor.startswith("human:")})
        summary["n_humans"] = len({e.actor for e in log.events if e.actor and e.actor.startswith("human:")})
        summary["village"] = getattr(log, "village", None)
        summary["active_days"] = len({int(e.ts // 86400) for e in log.events if e.ts is not None})
    out = dict(summary=summary, inference=inf, coordination=coord, info_spread=spread,
               covert=cov, early_warning=ew, research=res)
    if attributed:
        out["attributed"] = analyze_attributed(log)
    return out


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


def _hm(ts):
    return "-" if ts is None else _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%b %d %H:%M")


def _markdown_attributed(log: EventLog, f: dict) -> str:
    """Report for logs that name every speaker (AI Village).

    Each section appears only when the log has data for it, and every number
    in the text is computed from this log (no village-specific wording).
    """
    s, A = f["summary"], f["attributed"]
    timed = log.timed_events()
    hours = (timed[-1].ts - timed[0].ts) / 3600 if timed else 0
    chats = [e for e in log.events if e.kind == "chat"]
    agents = {e.actor for e in chats if e.actor and not e.actor.startswith("human:")}
    humans = [e for e in chats if e.actor and e.actor.startswith("human:")]
    rooms = Counter(e.channel for e in chats)
    top_room_share = rooms.most_common(1)[0][1] / len(chats) if chats else 0
    sec = [0]

    def H(title):
        sec[0] += 1
        L.append(f"## {sec[0]}. {title}\n")
        return sec[0]

    L = [f"# SwarmScope findings: `{getattr(log, 'village', None) or s['source']}`\n"]
    L.append(f"- Events: **{s['n_events']:,}** ({', '.join(f'{k}: {v:,}' for k, v in s['kinds'].items())})")
    if timed:
        span = f"{hours:.1f} h" if hours < 72 else f"{hours / 24:.0f} days"
        L.append(f"- Agents who spoke: **{len(agents)}**; chat messages: **{len(chats):,}** "
                 f"({len(humans):,} by humans); rooms: {len(rooms)} (largest holds {_pct(top_room_share)}); "
                 f"time span: **{span}** ({_hm(timed[0].ts)} to {_hm(timed[-1].ts)} UTC)")
    L.append("- Every event names its author and has a real time, so no inference is needed. "
             "A message that writes `@name` is an edge from the speaker to that agent. Humans appear only as "
             "anonymous ids (`human:` plus 8 characters).\n")
    ms = getattr(log, "milestones", {}) or {}
    lab = getattr(log, "milestone_labels", {}) or {}
    nh = getattr(log, "human_messages", 0)
    if ms and getattr(log, "milestone_source", None) == "village goal changes":
        L.append(f"**Milestones: {len(ms)} village goal changes.** Humans wrote {nh:,} messages here, too many to be "
                 "rare announcements, so we use the start of each new village goal as ground truth for "
                 "\"something changed\" (first ones shown):\n")
        L.append(_md_table(["milestone", "time (UTC)", "goal"],
                           [(k, _hm(v), lab.get(k, "")[10:]) for k, v in sorted(ms.items(), key=lambda x: x[1])[:8]]))
        L.append("")
    elif ms:
        nudges = getattr(log, "operator_nudges", 0)
        L.append("**Operator announcements** (humans post rarely, so their messages to everyone are ground truth "
                 "for \"something changed\"" + (f"; {nudges} personal nudges to single agents are left out" if nudges else "")
                 + "):\n")
        L.append(_md_table(["milestone", "time (UTC)", "first words"],
                           [(k, _hm(v), lab.get(k, "")[10:]) for k, v in sorted(ms.items(), key=lambda x: x[1])]))
        L.append("")
    elif nh:
        L.append(f"**No operator milestones.** Humans wrote {nh:,} messages here (in this village, viewers chat "
                 "with the agents), so human messages are not rare announcements and cannot serve as ground "
                 "truth. Change-point alerts below are unlabelled.\n")

    # ---- who talked to whom
    cv = A.get("conversation", {})
    if cv:
        H("Who talked to whom")
        o, la = cv["overall"], cv["latency"]
        if o["addresses"] < 50:
            L.append(f"Agents here rarely address each other with `@name` ({o['addresses']} addresses in all), "
                     "so the conversation network is too thin to measure.\n")
        else:
            L.append("`Gini` = how unequal incoming attention is (0 = equal, 1 = one agent gets all). "
                     "`reciprocity` = share of addressed pairs that address each other back.\n")
            if 1 < len(cv["phases"]) <= 12:
                rows = [(p["label"][:40], _hm(p["start"]), p["speakers"], p["addresses"], p["addresses_per_hour"],
                         p["reciprocity"], p["attention_gini"],
                         ", ".join(f"{a} ({n})" for a, n in p["hubs"][:3])) for p in cv["phases"]]
                L.append(_md_table(["phase (starts with)", "from", "speakers", "@-addresses", "per hour",
                                    "reciprocity", "Gini", "top hubs"], rows))
                L.append("")
            L.append(f"Whole log: {o['addresses']:,} addresses between {o['addressed_pairs']:,} pairs, reciprocity "
                     f"{o['reciprocity']}, Gini {o['attention_gini']}. Top hubs: "
                     + ", ".join(f"{a} ({n})" for a, n in o["hubs"][:4]) + f". {_pct(la['answered_frac'])} of "
                     f"addresses got an answer within 6 h (median {la['median_minutes']} min)."
                     + (" Brokers (betweenness): " + ", ".join(f"{a} ({v})" for a, v in o["brokers"][:5]) + "."
                        if o.get("brokers") else "") + "\n")

    # ---- side rooms
    rm = A.get("rooms") or {}
    if rm:
        H("Side rooms (could agents talk out of sight?)")
        side = [r for r in rm["table"] if not r["main"]]
        L.append(f"{rm['rooms']} rooms; {_pct(rm['side_room_message_share'])} of messages are outside the main room "
                 f"(`{rm['main_room']}`). A room counts as **private** when at most {rm['private_group_limit']} agents "
                 f"use it (the private-channel limit for a swarm of {rm['swarm_size']}) with at least a few messages. "
                 "`withdrawal` = share of its members' messages that went to the room on its active days. "
                 "`leaked` = coined items first used there that 3 or more agents later used in the main room.\n")
        L.append(_md_table(["room", "agent msgs", "agents", "active days", "withdrawal", "private?", "leaked items",
                            "examples"],
                           [(r["room"], r["agent_messages"], r["agents"], r["active_days"], _pct(r.get("withdrawal")),
                             "**yes**" if r.get("private") else "no", r.get("leaked_items", 0),
                             ", ".join(f"`{i}` ({n})" for i, n in r.get("leak_examples", [])[:3]))
                            for r in side[:10]]))
        L.append(f"\nPrivate rooms: **{len(rm['private_rooms'])}**"
                 + (f" ({', '.join(rm['private_rooms'])})" if rm["private_rooms"] else "") + ".\n")

    # ---- spread
    df = A.get("diffusion", {})
    if df:
        rows = []
        for kind in ("files", "commits", "terms"):
            for r in df.get(kind, [])[:5]:
                rows.append((kind[:-1], f"`{r['item'][:40]}`", r["origin"], r["reach"], r["hours_to_half"],
                             r["depth"], _pct(r["sourced_by_address"])))
        if rows or df.get("case_studies"):
            H("How information spread")
        if rows:
            L.append("Each item is a file name, a commit, or a coined identifier. For each agent we take its first "
                     "use. `source by @` = share of adopters whose probable source had addressed them before "
                     "(exposure model, Goel, Watts & Goldstein, 2012).\n")
            L.append(_md_table(["kind", "item", "first agent", "agents", "hours to half", "tree depth",
                                "source by @"], rows))
            L.append("")
        for name, c in (df.get("case_studies") or {}).items():
            L.append(f"**Case study `{name}`.** {c.get('question', '')}\n")
            if c.get("reach"):
                L.append(f"- From then to the end of the log: {c['messages']:,} messages by {c['reach']} agents; "
                         f"half of them within {c['hours_to_half']} h; first: {c['origin']} at "
                         f"{_hm(c['first_ts'])} UTC.")
            else:
                L.append("- No matching messages after it.")
            vc = c.get("vs_control")
            if vc:
                b, a = vc["before"], vc["after"]
                L.append(f"- Control window before: {b['matching']} of {b['messages']} messages "
                         f"({_pct(b['share'])}, {b['agents']} agents); same length after: {a['matching']} of "
                         f"{a['messages']} ({_pct(a['share'])}, {a['agents']} agents). "
                         + (f"Ratio **{vc['ratio']}** (1 = no change)." if vc['ratio'] is not None else
                            "**No matching messages in either window.**"))
                if name.startswith("role"):
                    L.append("- Caution: role talk also fades by itself once roles settle, so a drop does not "
                             "prove anything. But a reassignment that the agents noticed would give a rise.")
            L.append("")

    # ---- early warning
    cp = A.get("changepoint", {})
    H("Could it have flagged a change early?")
    if not cp.get("params"):
        L.append("Too few chat messages for the change-point detector (it needs at least 50).\n")
    else:
        p = cp["params"]
        L.append(f"Online change-point detector on chat: every {p['step']} min it compares the last "
                 f"{p['window']} min with the {p['baseline']} min before, on topic (Jensen-Shannon "
                 f"divergence of word counts) and volume (log rate ratio), each turned into a robust z-score "
                 f"against its own past"
                 + (" (for logs longer than 3 days: against the same hour on earlier days, so a daily schedule "
                    "is not an alert)" if p.get("daily_baseline") else "")
                 + f". Alert at |z| >= {p['z']}. Steps where either window is empty are skipped.\n")
        sc = cp.get("score", {})
        if sc:
            if len(sc["milestones"]) <= 12:
                L.append(_md_table(["milestone", "time (UTC)", "detected?", "delay (min)"],
                                   [(r["milestone"], _hm(r["ts"]), "yes" if r["detected"] else "**no**",
                                     r["delay_minutes"] if r["delay_minutes"] is not None else "-")
                                    for r in sc["milestones"]]))
            src = getattr(log, "milestone_source", None) or "milestones"
            L.append(f"\nDetected {sc['detected']} of {sc['total']} {src} (within "
                     f"{sc['tolerance_minutes']} min). Alerts that follow no announcement: {sc['false_alerts']} "
                     f"({sc.get('unlabeled_but_corroborated', 0)} corroborated by a change in non-chat actions, "
                     f"{sc.get('unexplained', 0)} unexplained).\n")
        al = cp["alerts"]
        days = max(hours / 24, 1e-9)
        kinds = Counter(a["why"] for a in al)
        L.append(f"{len(al)} alerts in all ({len(al) / days:.2f} per day): "
                 + ", ".join(f"{k} {v}" for k, v in kinds.most_common()) + ".\n")
        shown = al if len(al) <= 15 else sorted(al, key=lambda a: -max(a["z_topic"], abs(a["z_volume"])))[:15]
        if len(al) > 15:
            L.append("The 15 strongest:\n")
        L.append(_md_table(["alert (UTC)", "why", "z topic", "z volume", "new words", "non-chat actions changed"],
                           [(_hm(a["t"]), a["why"], a["z_topic"], a["z_volume"], ", ".join(a["top_new_words"][:4]),
                             "; ".join(a.get("corroborated_by", [])[:2]) or "-")
                            for a in sorted(shown, key=lambda a: a["t"])]))
        L.append("")
    dl = cp.get("daily") or {}
    if dl:
        q = dl["params"]
        L.append(f"**Day-level check** (for long logs). Each active day (at least {q['min_msgs']} agent messages) is "
                 f"compared with the {q['ref_days']} active days before it; alert at z >= {q['z']}. "
                 f"{len(dl['alert_days'])} alert days out of {dl['active_days']} active days.")
        if dl.get("milestones"):
            L.append(f"It flags **{dl['flagged']} of {dl['milestones']}** {getattr(log, 'milestone_source', None) or 'milestones'} "
                     f"within their first {q['lag']} active days ({_pct(dl['recall'])}, against {_pct(dl['chance'])} "
                     f"for any day), and {_pct(dl['precision'])} of its alert days fall in those windows."
                     + (" It is slow, but when it fires it is usually a real change." if (dl.get("precision") or 0) >= 0.8 else "")
                     + "\n")
        else:
            L.append("There are no milestones to score it against.\n")
    tc = f.get("early_warning", {}).get("timestamp_crosscheck", {})
    if tc.get("triggers"):
        L.append("**False-alarm load of the Swarm Traces signals.** No covert channel is known in this village, "
                 "so each firing is at best a lead for an investigator:\n")
        tph = tc.get("triggers_per_hour", {})
        L.append(_md_table(["signal", "firings", "per hour"],
                           [(k, v, tph.get(k)) for k, v in sorted(tc["triggers"].items(), key=lambda x: -x[1])]))
        L.append("")

    # ---- authority
    au = {r: v for r, v in (A.get("authority") or {}).items() if v.get("role_assigned_at")}
    if au:
        H("Authority mismatch (claims of a power that was not given)")
        for role, r in au.items():
            L.append(f"Role **{role}** was assigned at {_hm(r['role_assigned_at'])} UTC. Unassigned claimants: "
                     f"**{r['unassigned_claimants']}**. `endorsers` = distinct agents who addressed the claimant "
                     f"in a message that mentions the role.\n")
            if r.get("assigned_holder_endorsers") and r.get("compared_since"):
                L.append("Over the same window (from " + _hm(r["compared_since"]) + " UTC, the first unassigned claim), "
                         "the assigned holder was addressed in that role by "
                         + ", ".join(f"{a} ({n} agents)" for a, n in r["assigned_holder_endorsers"].items()) + ".\n")
            if r["claimants"]:
                L.append(_md_table(["claimant", "assigned?", "first claim (UTC)", "claim msgs", "endorsers",
                                    "hours to half", "endorsement via @"],
                                   [(c["agent"], "yes" if c["assigned"] else "**no**", _hm(c["first_claim"]),
                                     c["claim_messages"], c["endorsers"], c["endorsement_hours_to_half"],
                                     _pct(c["endorsement_via_address"])) for c in r["claimants"]]))
            L.append("")

    # ---- human influence
    inf = A.get("influence") or {}
    if inf:
        H("Did humans steer the agents?")
        a_, i_, j_ = inf["all_human"], inf["instructions"], inf["injection_like"]
        L.append(f"{inf['human_messages']:,} messages from {inf['humans']} humans. A human message is *taken up* when "
                 f"an agent message in the next {inf['window_minutes']} minutes reuses at least 2 of its rare words or "
                 "one of its links. Control: the same test on agent messages in the "
                 f"{inf['window_minutes']} minutes **before** it (an ongoing topic matches both).\n")
        L.append(_md_table(["human messages", "count scored", "taken up after", "matched before", "lift"],
                           [("all", a_["scored"], _pct(a_["rate_after"]), _pct(a_["rate_before"]), a_["lift"] or "-"),
                            ("instruction-like", i_["scored"], _pct(i_["rate_after"]), _pct(i_["rate_before"]), i_["lift"] or "-"),
                            ("injection-like", j_["scored"], _pct(j_["rate_after"]), _pct(j_["rate_before"]), j_["lift"] or "-")]))
        if j_["count"]:
            L.append(f"\nInjection-like messages (\"ignore previous instructions\", \"system prompt\", \"you are now\"...): "
                     f"{j_['count']}; an agent refused within the window after {j_['agent_refused_within_window']} of them.")
        if a_["lift"] is None and a_["scored"]:
            L.append(f"\nOnly {a_['scored']} human messages could be scored and none matched before, so no lift is given.")
        ac_ = inf.get("actions")
        if ac_ and ac_["human_introduced_links"]:
            L.append(f"\n**From words to actions.** {ac_['human_introduced_links']} links were first posted by a human "
                     f"(no agent had used them before). Agents opened or ran **{ac_['followed_in_actions_24h']}** of them "
                     f"({_pct(ac_['followed_share'])}) within 24 hours, {ac_['agents_who_followed']} agents in all. "
                     "Top domains: " + ", ".join(f"{d} ({n})" for d, n in ac_["top_followed_domains"][:6]) + ".")
        L.append("")

    # ---- emergence
    em = A.get("emergence") or {}
    if em:
        H("Is the group more than the sum of its agents? (Riedl's test)")
        L.append(f"Each agent's messages per {em['bin_minutes']}-minute bin, split at its median; the group total "
                 "likewise. **Practical criterion** S = I(V_t;V_t+1) - sum I(X_i,t;V_t+1) (> 0: the group predicts "
                 "its own future better than its members do). **Synergy** = median pairwise synergy of a "
                 "Williams-Beer decomposition of time-delayed mutual information; **redundancy** likewise. "
                 f"Null: {em['null']} ({em['permutations']} surrogates). Groups of {em['group_size']} agents, cut to "
                 "the time when all were active. This uses timing only, not content.\n")
        tg = em["top_group"]
        rows = []
        if "synergy_p" in tg:
            rows.append(("most active group", tg.get("transitions"), f"{tg['practical']} (p {tg['practical_p']})",
                         f"{tg['synergy_corrected']:+} (p {tg['synergy_p']})",
                         f"{tg['redundancy_corrected']:+} (p {tg['redundancy_p']})"))
        for i, r in enumerate(em.get("random_groups", [])[:10], 1):
            rows.append((f"random group {i}", r["transitions"], f"{r['practical']} (p {r['practical_p']})",
                         f"{r['synergy_corrected']:+} (p {r['synergy_p']})",
                         f"{r['redundancy_corrected']:+} (p {r['redundancy_p']})"))
        L.append(_md_table(["group", "transitions", "practical S", "synergy (minus null median)", "redundancy"], rows))
        if em.get("random_groups"):
            n_ = len(em["random_groups"])
            L.append(f"\nRandom groups significant at p < 0.05: synergy {em['random_groups_synergy_significant']}/{n_}, "
                     f"redundancy {em['random_groups_redundancy_significant']}/{n_}, practical criterion "
                     f"{em['random_groups_practical_significant']}/{n_}.\n")

    # ---- actions and memory
    ac = A.get("actions") or {}
    rd = ac.get("role_drift") or {}
    rb = ac.get("rule_breaks") or {}
    has_rd = rd.get("statements", 0) >= 10
    has_rule = bool(rb) and bool(au)
    ga = ac.get("goal_adoption") or {}
    if has_rd or rb or ga:
        H("What agents believed and did (memories and computer use)")
    if ga:
        L.append(f"**Goal adoption.** For each new village goal we take its 4 rarest words. A memory written during "
                 "the goal *mentions it* when it contains 2 of them; it is *stale* when it mentions only the previous "
                 f"goal's words. {ga['goals_scored']} goals with enough distinctive words are scored (open goals such as "
                 "\"pursue whatever you like\" cannot be). Median over goals: "
                 f"**{_pct(ga['median_adopted_share'])}** of active agents' memories mention the new goal, after a median "
                 f"**{ga['median_lag_hours']} h**; {_pct(ga['median_early_stale_share'])} of memories in the first 24 h are "
                 "stale.\n")
        worst = sorted([g for g in ga["goals"] if g["early_stale_share"] is not None],
                       key=lambda g: -g["early_stale_share"])[:5]
        L.append("Goals where agents kept the old goal longest:\n")
        L.append(_md_table(["goal", "start (UTC)", "key words", "agents", "mention it", "median lag (h)",
                            "stale in first 24 h"],
                           [(g["goal"], _hm(g["start"]), ", ".join(g["keywords"]), g["agents"], _pct(g["adopted_share"]),
                             g["median_lag_hours"], _pct(g["early_stale_share"])) for g in worst]))
        L.append("")
    if has_rd:
        L.append("**Role drift.** When an agent quotes its own goal (\"Play your assigned role: ...\", "
                 "\"Phase-2 role: ...\") in its memory or in a work-session goal, we compare the role it "
                 "names with the role it was assigned. An alert fires when "
                 f"{rd['params']['min_agents']} or more agents name a different role within "
                 f"{rd['params']['window']} minutes.\n")
        st_ = rd.get("strict") or {}
        L.append(f"- {rd['statements']:,} statements by {rd['agents_with_statements']} agents; "
                 f"{rd['mismatching']:,} name another role; {rd['agents_drifted']} agents drifted"
                 + (f" ({st_['agents_drifted']} with only the strictest phrases, \"assigned role\", \"Phase-2 role\", "
                    f"\"my role is\", and memories only)" if st_ else "") + ".")
        if st_ and not st_.get("statements"):
            L.append("- None of these statements uses the strictest phrases; all are looser matches (for example a "
                     "work-session goal naming a task), so treat them as weak evidence of drift.")
        if rd.get("alert"):
            ba = rd.get("before_alert", {})
            am = rd.get("after_milestone", {})
            L.append(f"- **Alert at {_hm(rd['alert'])} UTC**"
                     + (f", {am['delay_minutes']} min after operator message `{am['milestone']}` "
                        f"({lab.get(am['milestone'], '')[10:60]}…)" if am else "")
                     + (f", {rd['before_next_milestone_hours']} h before the next operator message"
                        if rd.get('before_next_milestone_hours') else "") + ".")
            L.append(f"- Before the alert window: {ba.get('mismatching', 0)} of {ba.get('statements', 0)} "
                     "statements named another role.")
            L.append("- First agents to drift: " + ", ".join(
                f"{a} ({_hm(t)}, now names \"{r}\")" for a, t, r, _ in rd["first_mismatch"][:4]) + ".")
        L.append("")
    if has_rule:
        role = next(iter(au))
        L.append(f"**Rule breaks in actions.** Rule: only the {role} may edit code; everyone else acts "
                 f"through the game's interface ({rb['interface_uses']:,} uses by {rb['interface_agents']} agents). "
                 f"We read {rb['commands']:,} shell commands. A commit counts as code when it stages `.py` "
                 "files, and as **landed** when git confirms the push or another agent later sees its hash "
                 "(in a git log, pull or show). This is a lower bound (`git add -A` names no files).\n")
        rows = [(r["agent"], "yes" if r["privileged"] else "**no**",
                 "yes" if r["agent"] in rb.get("unassigned_claimants", []) else "-",
                 r["attempts"], r["landed"], _hm(r["first"]), ", ".join(f"`{x}`" for x in r["files"][:2]))
                for r in rb["code"]]
        if rows:
            L.append(_md_table(["agent", f"assigned {role}?", f"claimed {role}?", "code commits tried", "landed",
                                "first (UTC)", "files"], rows))
        ws = rb.get("world_state") or []
        L.append(f"\nCode reached the shared repository from {len(rb['code_landed_unprivileged'])} agents "
                 f"who were not the assigned {role}"
                 + (f": {', '.join(rb['code_landed_unprivileged'])}" if rb['code_landed_unprivileged'] else "")
                 + f". Direct commits of the world-state file (bypassing the interface): "
                 f"{sum(r['attempts'] for r in ws)} tried by {len(ws)} agents, {sum(r['landed'] for r in ws)} landed.\n")
    elif rb:
        L.append(f"**Actions.** We read {rb['commands']:,} shell commands ({rb['other_commits']:,} commits). This "
                 "village assigns no privileged role, so there is no permission rule to check them against.\n")

    # ---- blind spots
    H("What an investigator would still miss")
    pts = []
    rc = (df.get("case_studies") or {}).get("role_confusion", {}).get("vs_control") if df else None
    if rc:
        drift_txt = (f" Their memories show it: the role-drift alert fires at {_hm(rd['alert'])} UTC."
                     if rd.get("alert") else "")
        pts.append("**Changes that never reach the chat.** After an operator message reassigned roles, "
                   f"role-change messages went from {rc['before']['matching']} of {rc['before']['messages']} to "
                   f"{rc['after']['matching']} of {rc['after']['messages']}: the agents did not discuss it."
                   + drift_txt + " An investigator needs the agents' memories or goals, not only their messages.")
    if not ms:
        pts.append("**No ground truth for alerts.** Without rare operator announcements, nothing tells us which "
                   "change-point alerts were real events; each one needs a human to read the chat around it.")
    if au:
        pts.append("**Claims are found by phrase.** The authority detector reads phrases such as \"X claims god\". "
                   "An agent that acts with a power without saying so is missed.")
    if rb:
        pts.append("**What commands changed.** A commit made with `git add -A` does not name its files, so code "
                   "edits are a lower bound. Screenshots are not used.")
    else:
        pts.append("**Actions are missing.** Without the computer-use turns we see what agents said they did, "
                   "not what they did.")
    if has_rd:
        pts.append("**Role drift is found by phrase.** It needs an agent to quote its goal (\"assigned role: X\"); "
                   "agents that switched without writing it down are missed.")
    elif not ac.get("role_drift"):
        pts.append("**Beliefs are missing.** Without agent memories we cannot compare what agents believe their "
                   "goal is with what they were assigned.")
    if nh and A.get("influence"):
        pts.append("**Influence is measured by reuse, not cause.** An agent that reuses a viewer's words or link "
                   "may have found them elsewhere; the window before each message only removes ongoing topics.")
    elif nh:
        pts.append(f"**Humans in the loop.** Humans wrote {nh:,} messages. We do not check whether a human "
                   "message steered an agent (for example an instruction from a viewer), which is a known "
                   "risk for agents that read untrusted text.")
    pts.append("**`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the "
               "network undercounts who listened to whom.")
    if top_room_share >= 0.9:
        pts.append(f"**Mostly one room** ({_pct(top_room_share)} of messages), so there are few private side "
                   "channels to find. Coordination here is open, not covert.")
    L.append("\n\n".join(f"- {p}" for p in pts))
    if s.get("source") == "ai_village" or getattr(log, "village", None):
        L.append("\nData: AI Village by AI Digest (research use; see `PROJECT_PLAN.md` for terms and all sources).")
    else:
        L.append("\nSee `PROJECT_PLAN.md` for all data sources.")
    return "\n".join(x for x in L if x is not None)


def to_markdown(log: EventLog, f: dict) -> str:
    if f.get("attributed"):
        return _markdown_attributed(log, f)
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
