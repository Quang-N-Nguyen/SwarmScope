"""SwarmScope -- forensics and visualization for multi-agent logs.

Reconstructs who-talked-to-whom, how information spread, and which covert
channels were used in real multi-agent logs, then renders a dynamic graph that
changes over time.

Typical use from Python::

    from swarmscope.loaders import swarm_traces
    from swarmscope import graph, report

    log = swarm_traces.load("redacted.jsonl.gz")
    findings = report.analyze(log)
    report.write_outputs(log, findings, "outputs/swarm_traces")

Or from the command line::

    python -m swarmscope.cli analyze redacted.jsonl.gz --format swarm_traces --out outputs/swarm_traces
"""

__version__ = "0.1.0"
