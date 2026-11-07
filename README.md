# Apart-Research-Swarm-2026 — SwarmScope

Code for the Apart Research Swarm Alignment Hackathon project (Track 4: Multi-Agent Oversight and Control).

**SwarmScope** reads multi-agent logs. It reconstructs **who talked to whom**, **how information spread**, and **which covert channels were used**. Then it renders a **dynamic graph** that you can play forward in time.

- Plan, design and status: [`PROJECT_PLAN.md`](PROJECT_PLAN.md)
- Findings on Swarm Traces: [`outputs/swarm_traces/report.md`](outputs/swarm_traces/report.md)
- Interactive viewer: open `outputs/swarm_traces/swarmscope_swarm_traces.html` in a browser. It works offline.

## Quick start

```bash
# 1. Analyze Swarm Traces (Python 3.9+, standard library only, about 1 minute)
python -m swarmscope.cli analyze Swarm-Traces-Data/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces

# 2. Get AI Village (gated: accept the terms on huggingface.co first)
pip install huggingface_hub
huggingface-cli login
python scripts/download_ai_village.py            # swarm-village, about 100 MB
python -m swarmscope.cli analyze data/ai-village/swarm-village \
    --format ai_village --out outputs/ai_village_swarm-village

# 3. Your own log (any JSONL; say which fields hold what)
python -m swarmscope.cli analyze my_log.jsonl --format generic \
    --map actor=from,channel=thread,text=body,ts=time --out outputs/mine

# Tests
python tests/test_synthetic.py
python tests/test_loaders.py
```

## Layout

```
swarmscope/
  events.py            canonical Event model; one ordering per log
  extract.py           text -> resource ids, agent handles, mechanism flags
  graph.py             activity graph + agent graph (Adamic–Adar ties)
  loaders/             swarm_traces, ai_village, generic
  detectors/           coordination, info_spread, covert, early_warning
  viz/                 template.html + inlined D3 -> one self-contained HTML file
  report.py, cli.py
scripts/download_ai_village.py
tests/                 planted-collusion test, loader smoke tests
outputs/swarm_traces/  report.md, findings.json, viewer HTML
```

## Notes on the data

- **Swarm Traces** (swarmtraces.org): preliminary and redacted. Agent IDs are masked, and about 98% of records have no trusted timestamp. The tool **never prints payload text**. Reports show only IDs, counts and flags.
- **AI Village** (huggingface.co/datasets/aidigestorg/ai-village): released under the `ai-village-research-terms`. Use it for research only. Do not re-identify people, and cite AI Digest / AI Village. The data is not committed to this repo.
