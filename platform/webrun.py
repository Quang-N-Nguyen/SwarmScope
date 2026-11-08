"""Browser entry point for SwarmScope (runs inside Pyodide)."""
import json, sys, time
sys.path.insert(0, "/app")
from swarmscope.cli import _load
from swarmscope import report


def run(path, fmt, fmap="", inference="off", title=None):
    t0 = time.time()
    print("Loading the log...", file=sys.stderr)
    log = _load(fmt, path, None, fmap)
    print(f"Loaded {len(log):,} events. Running detectors...", file=sys.stderr)
    findings = report.analyze(log, prefer_time=True, inference=inference)
    print("Building the viewer...", file=sys.stderr)
    paths = report.write_outputs(log, findings, "/out", True, title, link_views=False)
    s = findings["summary"]
    out = dict(html=open(paths["html"]).read(), world=open(paths["world"]).read(), report=open(paths["report"]).read(),
               seconds=round(time.time() - t0, 1),
               summary={k: s.get(k) for k in ("n_events", "n_named_agents", "n_ai_agents", "n_humans",
                                              "n_shared_deaddrops", "active_days")})
    return json.dumps(out, default=str)
