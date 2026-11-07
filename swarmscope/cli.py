"""Command-line entry point.

Examples
--------
Swarm Traces::

    python -m swarmscope.cli analyze path/to/redacted.jsonl.gz \\
        --format swarm_traces --out outputs/swarm_traces

AI Village (after you have downloaded it)::

    python -m swarmscope.cli analyze path/to/swarm-village \\
        --format ai_village --out outputs/ai_village

Any JSONL log with a field map::

    python -m swarmscope.cli analyze log.jsonl --format generic \\
        --map actor=from,channel=thread,text=body,ts=time --out outputs/mine
"""

from __future__ import annotations

import argparse
import sys

from .loaders import swarm_traces, ai_village, generic
from . import report


def _load(fmt: str, path: str, limit, field_map):
    if fmt == "swarm_traces":
        return swarm_traces.load(path, limit=limit)
    if fmt == "ai_village":
        return ai_village.load(path, limit=limit)
    if fmt == "generic":
        fm = {}
        for pair in (field_map or "").split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                fm[k.strip()] = v.strip()
        return generic.load(path, fm, limit=limit)
    raise SystemExit(f"unknown --format {fmt!r}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="swarmscope")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="run all detectors and write report + viz")
    a.add_argument("input")
    a.add_argument("--format", required=True,
                   choices=["swarm_traces", "ai_village", "generic"])
    a.add_argument("--out", required=True, help="output directory")
    a.add_argument("--map", default=None, help="generic field map, e.g. actor=from,text=body")
    a.add_argument("--limit", type=int, default=None, help="load only first N records")
    a.add_argument("--sequence", action="store_true",
                   help="force reconstruction-order axis even if timestamps exist")
    a.add_argument("--title", default=None)
    a.add_argument("--inference", default="balanced",
                   choices=["off", "precise", "balanced", "broad"],
                   help="how far to infer missing authors and dates (see report.PRESETS)")

    args = p.parse_args(argv)
    if args.cmd == "analyze":
        log = _load(args.format, args.input, args.limit, args.map)
        prefer_time = not args.sequence
        print(f"[swarmscope] loaded {len(log):,} events from {args.input}", file=sys.stderr)
        findings = report.analyze(log, prefer_time=prefer_time, inference=args.inference)
        paths = report.write_outputs(log, findings, args.out, prefer_time, args.title)
        print("[swarmscope] wrote:", file=sys.stderr)
        for k, v in paths.items():
            print(f"  {k}: {v}", file=sys.stderr)
        s = findings["summary"]
        print(f"[swarmscope] {s['n_events']:,} events | {s['n_named_agents']} named agents | "
              f"{s['n_shared_deaddrops']} shared dead-drops", file=sys.stderr)


if __name__ == "__main__":
    main()
