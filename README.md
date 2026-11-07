# Apart-Research-Swarm-2026 — SwarmScope

Code for the Apart Research Swarm Alignment Hackathon project (Track 4: Multi-Agent Oversight and Control).

**SwarmScope** reads multi-agent logs. It reconstructs **who talked to whom**, **how information spread**, and **which covert channels were used**. Then it renders a **dynamic graph** that you can play forward in time.

When names and times are missing (as in the redacted Swarm Traces data), SwarmScope **infers** them from shared rare identifiers, and it reports how often each guess is wrong on held-out data. Inferred names are 95% precise, and 94% of inferred dates fall within 24 h. Inferred values are always shown apart from observed ones.

- Plan, design, results, and all sources: [`PROJECT_PLAN.md`](PROJECT_PLAN.md)
- Findings on Swarm Traces: [`outputs/swarm_traces/report.md`](outputs/swarm_traces/report.md)
- Findings on AI Village `swarm-village`: [`outputs/ai_village_swarm-village/report.md`](outputs/ai_village_swarm-village/report.md)
- The other AI Village villages (control logs): `outputs/ai_village_<village>/report.md`, compared in [`outputs/ai_village_comparison.md`](outputs/ai_village_comparison.md)
- One combined alert across all logs (lead time vs false alarms): [`outputs/flag_early.md`](outputs/flag_early.md)
- Real external log through the generic loader (Transluce agent-activity reports): [`outputs/transluce/report.md`](outputs/transluce/report.md)
- Independent review of the headline claims, and blind-labelled precision/recall: [`review/`](review/)
- Interactive viewers: open `outputs/*/swarmscope_*.html` in a browser. They work offline. Use **Follow an item** to watch a file, commit, coined term or role claim spread from agent to agent.

When most events already name their author (AI Village), SwarmScope skips inference and adds detectors for the conversation network by phase, information diffusion, online change points, authority mismatch (an agent claiming a role it was not given), role drift (agents' own goals vs their assigned roles) and rule breaks in their shell commands. It also checks side rooms (private groups, items leaking into the main room), human influence (did viewers' messages and links change what agents said and did), goal adoption after a village goal changes, and Riedl's information-theoretic emergence test. On `swarm-village` it catches an unassigned agent claiming the "god" role (73 agents followed it), and, from the agents' memories, an operator error that silently reassigned every role (alert 12 minutes after it; the chat never mentioned it). See `PROJECT_PLAN.md` §10. In the viewer, the **Forensics charts** button shows these results on one clock: change-detector scores, role talk around the reshuffle, the agents' own goals drifting after it, who the swarm treated as god, and how files, commits and coined terms spread.

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

# 4. Everything for AI Village (all four villages), then the cross-log scores
for v in swarm-village game-jam-village open-chat-village main-village; do
  python -m swarmscope.cli analyze data/ai-village/$v --format ai_village --out outputs/ai_village_$v
done
python scripts/compare_villages.py      # one table across villages
python scripts/flag_early.py            # one combined alert: lead time vs false alarms

# 5. Transluce (download the zip from transluce.org/agent-activity and unzip it into data/transluce)
python scripts/transluce_to_jsonl.py data/transluce/urlquery-agent-activity-2026-09-22-v5 data/transluce/reports.jsonl
python -m swarmscope.cli analyze data/transluce/reports.jsonl --format generic \
    --map actor=source,channel=evidence_class,text=text,ts=time,kind=confidence,id=id --out outputs/transluce

# Tests
python tests/test_synthetic.py
python tests/test_loaders.py
python tests/test_detectors.py
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
                       + for named-speaker logs: conversation, diffusion, changepoint, authority, actions,
                         rooms, influence, emergence
  viz/                 template.html + inlined D3 -> one self-contained HTML file
  report.py, cli.py
scripts/               download_ai_village, sweep_inference, compare_villages, flag_early, transluce_to_jsonl
tests/                 planted-collusion and tie-test checks, loader tests, one test per detector
review/                independent review, blind-label scores, draft Swarm Traces access request
outputs/swarm_traces/, outputs/ai_village_swarm-village/   report.md, findings.json, viewer HTML
```

## Notes on the data

- **Swarm Traces** (swarmtraces.org): preliminary and redacted. Agent IDs are masked, and only 3.1% of records carry a trusted date. The tool **never prints payload text**. Reports show only IDs, counts and flags.
- **AI Village** (huggingface.co/datasets/aidigestorg/ai-village): released under the `ai-village-research-terms`. Use it for research only. Do not re-identify people, and cite AI Digest / AI Village. The data is not committed to this repo. Humans appear only as anonymous ids; reports show link domains, never message text from viewers.
- **Transluce** (transluce.org/agent-activity): public report links and metadata, no agent field. It tests the generic loader; who-talked-to-whom cannot be rebuilt from it.
