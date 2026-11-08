"""Accuracy vs coverage for each inference preset (held-out tests).

Run from the repo root:

    python scripts/sweep_inference.py data/swarm-traces/redacted.jsonl.gz

For each preset in swarmscope.report.PRESETS it prints:
  * attribution: held-out precision and coverage, and the share of all events
    that end up with a name;
  * dating: held-out error (median, 80th, 90th percentile, share within 24 h),
    coverage, and the share of all events that end up with a time.

Each preset is run on a fresh copy of the log, so the presets do not affect
each other. Takes a few minutes (most of it is loading the data).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarmscope.loaders import swarm_traces          # noqa: E402
from swarmscope.infer import links, attribution, dating  # noqa: E402
from swarmscope.report import PRESETS                # noqa: E402


def main(path: str) -> None:
    print("| preset | names: precision | names: coverage | events named | dates: median err (h) | p80 (h) | p90 (h) | within 24 h | events dated |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name, p in PRESETS.items():
        log = swarm_traces.load(path)
        n = len(log)
        La = links.build(log, max_events=p["attr_T"])
        ae = attribution.evaluate(log, La, **p["attr"])["all"]
        ar = attribution.run(log, La, **p["attr"])
        Ld = La if p["date_T"] == p["attr_T"] else links.build(log, max_events=p["date_T"])
        de = dating.evaluate(log, Ld, **p["date"])
        dr = dating.run(log, Ld, **p["date"])
        print(f"| {name} | {ae['precision']} | {ae['coverage']} | {ar['named_total_frac']*100:.1f}% | "
              f"{de['error_hours_median']} | {de['error_hours_p80']} | {de['error_hours_p90']} | "
              f"{de['within_24h']*100:.1f}% | {dr['dated_total_frac']*100:.1f}% |", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/swarm-traces/redacted.jsonl.gz")
