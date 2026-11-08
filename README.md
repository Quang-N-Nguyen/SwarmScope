# SwarmScope

Dynamic-graph forensics and early warning for multi-agent logs. Apart Research Swarm Alignment Hackathon, Track 4 (Multi-Agent Oversight and Control).

SwarmScope reads a multi-agent log and rebuilds who talked to whom, how information spread and which covert channels were used. It plays the result forward as a dynamic graph and replays the log online to test whether the coordination could have been flagged early. When names and times are redacted, it infers them and reports its error on held-out data.

- **Paper and results:** [`PROJECT.md`](PROJECT.md)
- **Results page:** open [`index.html`](index.html) in a browser: five findings, each linked to the viewer view that shows it
- **Platform (workbench):** explore the six viewers, or run SwarmScope on your own log in the browser (Pyodide; the file never leaves the browser). Build it with `python platform/build_platform.py` and serve `platform/build/`
- **Viewers:** open `outputs/*/swarmscope_*.html` in a browser (works offline)
- **Reports:** `outputs/*/report.md`; across villages: [`outputs/ai_village_comparison.md`](outputs/ai_village_comparison.md); combined alert: [`outputs/flag_early.md`](outputs/flag_early.md)

## Quick start

```bash
# Swarm Traces (Python 3.9+, standard library only, about 1 minute)
mkdir -p data/swarm-traces && curl -L https://swarmtraces.org/data/final/redacted.jsonl.gz -o data/swarm-traces/redacted.jsonl.gz
python -m swarmscope.cli analyze data/swarm-traces/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces --inference balanced
#   --inference: off | precise | balanced | broad
python scripts/sweep_inference.py data/swarm-traces/redacted.jsonl.gz   # accuracy per preset

# AI Village (gated: accept the terms on huggingface.co, then log in)
pip install huggingface_hub && huggingface-cli login
python scripts/download_ai_village.py --village swarm-village \
    --tables chat_messages,chat_rooms,agents,events,computer_use_sessions,village_goals,agent_goals,villages,agent_memories,computer_use_turns
for v in swarm-village game-jam-village open-chat-village main-village; do
  python -m swarmscope.cli analyze data/ai-village/$v --format ai_village --out outputs/ai_village_$v
done
python scripts/compare_villages.py      # one table across villages
python scripts/flag_early.py            # combined alert: lead time vs false alarms
python scripts/validate_mission.py      # mission tests with known answers -> outputs/validation.json

# Transluce (unzip the release from transluce.org/agent-activity into data/transluce)
python scripts/transluce_to_jsonl.py data/transluce/urlquery-agent-activity-2026-09-22-v5 data/transluce/reports.jsonl
python -m swarmscope.cli analyze data/transluce/reports.jsonl --format generic \
    --map actor=source,channel=evidence_class,text=text,ts=time,kind=confidence,id=id --out outputs/transluce

# Any JSONL log
python -m swarmscope.cli analyze my_log.jsonl --format generic \
    --map actor=from,channel=thread,text=body,ts=time --out outputs/mine

# Tests
python tests/test_synthetic.py && python tests/test_loaders.py && python tests/test_detectors.py
```

## Layout

```
swarmscope/
  events.py, extract.py, graph.py   event model, text -> resources and flags, activity and agent graphs
  loaders/                          swarm_traces, ai_village, generic
  infer/                            evidence links, attribution, dating, aliases
  detectors/                        coordination, info_spread, covert, early_warning, research,
                                    conversation, diffusion, changepoint, authority, actions,
                                    rooms, influence, emergence
  viz/                              template.html + inlined D3 -> one offline HTML viewer
  report.py, cli.py
scripts/                            download, sweep_inference, compare_villages, flag_early, validate_mission, transluce_to_jsonl
tests/                              synthetic, loader and detector tests
docs/figures/                       figures used in PROJECT.md
platform/                           in-browser workbench: page, entry point, sample log, build script
outputs/<log>/                      report.md + viewer HTML (findings.json is regenerated, not committed)
```

## Data

- **Swarm Traces** ([swarmtraces.org](https://swarmtraces.org/)): redacted by its authors; download it into `data/swarm-traces/` (not committed). The tool never prints payload text.
- **AI Village** ([dataset](https://huggingface.co/datasets/aidigestorg/ai-village)): research use only under `ai-village-research-terms`; no re-identification; cite AI Digest. Not committed.
- **Transluce** ([agent activity](https://transluce.org/agent-activity)): public report metadata; no agent field.
