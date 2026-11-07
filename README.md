# Apart-Research-Swarm-2026 — SwarmScope

Code for the Apart Research Swarm Alignment Hackathon project (Track 4: Multi-Agent Oversight and Control).

**SwarmScope** reads multi-agent logs. It reconstructs **who talked to whom**, **how information spread**, and **which covert channels were used**. Then it renders a **dynamic graph** that you can play forward in time.

When names and times are missing (as in the redacted Swarm Traces data), SwarmScope **infers** them from shared rare identifiers, and it reports how often each guess is wrong on held-out data. Inferred names are 95% precise, and 94% of inferred dates fall within 24 h. Inferred values are always shown apart from observed ones.

- Plan, design, results, and all sources: [`PROJECT_PLAN.md`](PROJECT_PLAN.md)
- Findings on Swarm Traces: [`outputs/swarm_traces/report.md`](outputs/swarm_traces/report.md)
- Findings on AI Village `swarm-village`: [`outputs/ai_village_swarm-village/report.md`](outputs/ai_village_swarm-village/report.md)
- The other AI Village villages (control logs): `outputs/ai_village_<village>/report.md`, compared in [`outputs/ai_village_comparison.md`](outputs/ai_village_comparison.md)
- Interactive viewers: open `outputs/*/swarmscope_*.html` in a browser. They work offline.

When most events already name their author (AI Village), SwarmScope skips inference and adds detectors for the conversation network by phase, information diffusion, online change points, authority mismatch (an agent claiming a role it was not given), role drift (agents' own goals vs their assigned roles) and rule breaks in their shell commands. On `swarm-village` it catches an unassigned agent claiming the "god" role (73 agents followed it), and, from the agents' memories, an operator error that silently reassigned every role (alert 12 minutes after it; the chat never mentioned it). See `PROJECT_PLAN.md` §10. In the viewer, the **Forensics charts** button shows these results on one clock: change-detector scores, role talk around the reshuffle, the agents' own goals drifting after it, who the swarm treated as god, and how files, commits and coined terms spread.

## Quick start

```bash
# 1. Analyze Swarm Traces (Python 3.9+, standard library only, about 1 minute)
python -m swarmscope.cli analyze Swarm-Traces-Data/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces --inference balanced
#    --inference: off | precise | balanced | broad (accuracy table in PROJECT_PLAN.md §7)

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
  infer/               links (evidence graph), attribution, dating, aliases
  detectors/           coordination, info_spread, covert, early_warning, research
                       + for named-speaker logs: conversation, diffusion, changepoint, authority, actions
  viz/                 template.html + inlined D3 -> one self-contained HTML file
  report.py, cli.py
scripts/download_ai_village.py, scripts/sweep_inference.py
tests/                 planted-collusion and tie-test checks, loader smoke tests
outputs/swarm_traces/, outputs/ai_village_swarm-village/   report.md, findings.json, viewer HTML
```

## Notes on the data

- **Swarm Traces** (swarmtraces.org): preliminary and redacted. Agent IDs are masked, and only 3.1% of records carry a trusted date. The tool **never prints payload text**. Reports show only IDs, counts and flags.
- **AI Village** (huggingface.co/datasets/aidigestorg/ai-village): released under the `ai-village-research-terms`. Use it for research only. Do not re-identify people, and cite AI Digest / AI Village. The data is not committed to this repo.
