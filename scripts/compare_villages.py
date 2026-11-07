"""Compare SwarmScope results across AI Village villages.

Reads outputs/ai_village_<village>/findings.json (run the CLI on each village
first) and writes outputs/ai_village_comparison.md: one row per village.

    python scripts/compare_villages.py
"""

import glob
import json
import os
import sys

OUT = "outputs"


def row(path):
    f = json.load(open(path))
    s, A = f["summary"], f.get("attributed") or {}
    name = os.path.basename(os.path.dirname(path)).replace("ai_village_", "")
    cv = (A.get("conversation") or {}).get("overall") or {}
    cp = A.get("changepoint") or {}
    tc = (f.get("early_warning") or {}).get("timestamp_crosscheck") or {}
    trig, tph = tc.get("triggers") or {}, tc.get("triggers_per_hour") or {}
    hours = tc.get("hours") or 0
    au = A.get("authority") or {}
    claim = sum(r.get("unassigned_claimants", 0) for r in au.values())
    rd = (A.get("actions") or {}).get("role_drift") or {}
    sc = cp.get("score") or {}
    chat = s["kinds"].get("chat", 0)
    return dict(
        village=name,
        agents=s.get("n_ai_agents"),
        humans=s.get("n_humans"),
        chat=chat,
        days=round(hours / 24, 1) if hours else None,
        addresses=cv.get("addresses"),
        reciprocity=cv.get("reciprocity"),
        gini=cv.get("attention_gini"),
        cp_alerts_per_day=round(len(cp.get("alerts") or []) / (hours / 24), 2) if hours else None,
        cp_detected=f"{sc['detected']}/{sc['total']}" if sc else "-",
        daily=(f"{(cp.get('daily') or {}).get('flagged')}/{(cp.get('daily') or {}).get('milestones')} (precision {(cp.get('daily') or {}).get('precision')})" if (cp.get("daily") or {}).get("milestones") else "-"),
        private_per_hour=tph.get("private_channel"),
        shared_per_hour=tph.get("shared_deaddrop"),
        claimants=claim if au else "-",
        drift_alert="yes" if rd.get("alert") else ("no" if (rd.get("statements") or 0) >= 10 else "-"),
    )


def main():
    rows = [row(p) for p in sorted(glob.glob(os.path.join(OUT, "ai_village_*", "findings.json")))]
    if not rows:
        sys.exit("no findings yet: run swarmscope.cli analyze on each village first")
    cols = [("village", "village"), ("agents", "agents"), ("humans", "humans"), ("chat", "chat msgs"), ("days", "days"),
            ("addresses", "@-addresses"), ("reciprocity", "reciprocity"), ("gini", "attention Gini"),
            ("cp_alerts_per_day", "change alerts / day"), ("cp_detected", "milestones caught (30 min)"), ("daily", "milestones caught (day level)"),
            ("private_per_hour", "private-channel firings / h"), ("shared_per_hour", "shared-resource firings / h"),
            ("claimants", "unassigned role claimants"), ("drift_alert", "role-drift alert")]
    lines = ["# SwarmScope across AI Village villages\n",
             "One row per village. `-` = not applicable (no operator announcements, no privileged role, "
             "or no memories downloaded).\n",
             "| " + " | ".join(h for _, h in cols) + " |", "|" + " --- |" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join("-" if r[k] is None else (f"{r[k]:,}" if isinstance(r[k], int) else str(r[k]))
                                        for k, _ in cols) + " |")
    out = os.path.join(OUT, "ai_village_comparison.md")
    open(out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote", out)


if __name__ == "__main__":
    main()
