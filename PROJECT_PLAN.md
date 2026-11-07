# Project plan: SwarmScope

**Apart Research hackathon, Track 4 (Multi-Agent Oversight and Control).**
Last updated: 2026-11-07.

## 1. Goal

We build a tool that reads multi-agent logs and shows three things:

1. **Who talked to whom.** This is a graph of interactions.
2. **How a piece of information spread.** This is a cascade over time.
3. **Which covert channels the agents used.** A covert channel is a hidden way to send data, for example data that is drawn into the pixels of a screenshot.

The output is a **dynamic graph**. It changes over time. Each edge is one interaction. You can play the graph forward, stop at any moment, and click a node to see what that agent did.

We also test one question: **could the tool have flagged the coordination early?** Then we write down what an investigator would still miss.

## 2. Research question

> Using Swarm Traces or the AI Village transcripts, can we build a tool that finds coordination, information spread, or covert channels in real multi-agent logs?

Why it matters: the Hugging Face swarm was found weeks after the fact (METR, 2026). Oversight that looks at one agent at a time does not scale to 700 agents. A group-level forensic tool is something that deployers and auditors can use now.

## 3. Data

| Source | Status | What it gives us | Main limit |
|---|---|---|---|
| **Swarm Traces** (`Swarm-Traces-Data/redacted.jsonl.gz`) | Loaded. 189,579 records. | Payloads, decoded layers and responses from the swarm that attacked Hugging Face in July 2026. | `agent_id` is redacted. About 98% of records have no trusted timestamp. About 80% of the data is outbound. |
| **AI Village** (huggingface.co/datasets/aidigestorg/ai-village) | **Not yet downloaded. The dataset is gated.** | Attributed chat: speaker, room, time. This is a mostly benign control log, which we can use to measure false alarms. | You must log in and accept the research terms first. Then run `scripts/download_ai_village.py`. |
| Transluce agent activity | Optional | Web activity logs. | Not scoped yet. |

**Swarm Traces record format.** Each record has these fields: `id, cite, kind, parent_id, time_utc, tags, text`.
- `kind` is `payload` (91,037), `recovered_text` (75,534, a decoded layer) or `response` (23,008).
- `parent_id` links 61,125 decoded layers and responses back to their payload. The chains are only one level deep.
- `time_utc` is always empty.
- Secrets and hosts are replaced by numbered tokens, for example `[CREDENTIAL 1]` and `[REDACTED:destination:000002]`. These tokens are what we use to link records.

## 4. Core idea (why the tool works the way it does)

In Swarm Traces, we cannot read a "from" field, because the sender is redacted. So we reconstruct interaction through **shared resources**. If two agents used the same dataset, mailbox or credential, they interacted *through* it. This is called a **dead-drop**: a place where one agent leaves data and another picks it up.

A small example with real numbers from the data:

- The resource `destination:000002` appears in 5,666 records, and 70 named agents use it.
- 56% of those records are ordinary calls to the task's own submission API. Every agent was *given* this API, so this sharing is **not** evidence of coordination.
- `destination:002666` is used by only 16 agents, and only 3% of its records are task traffic. Its records show Kubernetes activity and lock/kill activity. This sharing **is** telling.

The tool must tell these two cases apart. Section 5 describes how.

## 5. Pipeline

```
log file ─► loader ─► events ─► graphs ─► detectors ─► report.md + findings.json + viewer.html
```

1. **Loader.** One loader per format: `swarm_traces`, `ai_village`, and `generic` (any JSONL file plus a field map). Each loader converts the log into the same `Event` objects. An event records who did it (`actor`), the channel it went through (`channel`), the resources it touched (`refs`), mechanism flags (`features`), and a time.
2. **Agent names.** Swarm agents signed their message-board entries, for example `zzFILE_URI23816D_PUSH`. We read a handle such as `URI23816D` from these entries. This gives 286 named agents. The other ~99% of events have no named author.
3. **Order.** File order is grouped by record kind, so it is **not** time. We use an *estimated order*: events are sorted by the first-seen number of the resources they reference. This order correlates only about 0.4–0.5 with the real dates. For a real-clock check, we use the 3,780 events that have a trusted date inside the incident window.
4. **Graphs.**
   - *Activity graph*: agents and the resources they touch.
   - *Coordination graph*: agent to agent. Each tie is scored with **Adamic–Adar**. A shared resource adds `1/log(1+k)`, where `k` is the number of agents that use it. So a resource that everyone uses adds little, and a resource that only two agents share adds a lot.
5. **Detectors.**
   - *Coordination*: shared dead-drops (with task-API share), telling pairs, communities, swarm self-management (locks, killing rival controllers), and probable aliases (one agent with several names).
   - *Information spread*: for each credential or dataset, who touched it, in order, and how far it reached.
   - *Covert channels*: an inventory of 16 mechanism flags, with counts and the first time each one appears. One flag, `task_submit`, is the benign baseline. It marks ordinary task traffic.
   - *Early warning*: an **online** replay. At each step, the detector uses only what it has seen so far.
6. **Viewer.** One self-contained HTML file. D3 is included in the file, so it opens offline. It has a time slider, play/pause, Activity and Coordination views, a tie-strength filter, a mechanism highlight, and signal markers on the timeline.

## 6. First results on Swarm Traces

Full report: `outputs/swarm_traces/report.md`. Viewer: `outputs/swarm_traces/swarmscope_swarm_traces.html`.

- **Who talked to whom.** 286 named agents and 41 dead-drops shared by 2 or more named agents. If you keep only the strong ties (Adamic–Adar ≥ 0.99), 56 of 4,933 ties remain, and most of them are inside one community. The agents in the top telling pairs (MINIZJ11A, HOEXTN32, GEOS33474, WT8592N) are the same agents that rank highest for swarm self-management. These are two independent signals, and they agree.
- **Information spread.** `credential:1` reaches 66 named agents across 6,083 records. Section 4 explains why this sharing is task infrastructure and not collusion. The Kubernetes credential `credential:170` reaches 28 agents.
- **Covert channels.** Link-shortener chains (37,430 events), read-back through images (10,987), lock/duplicate control (4,919), signed commands (2,444), board writes (1,936), mailboxes (801), DNS exfiltration (791).
- **Early warning (real clock).** The structure-only *private channel* signal is a resource used repeatedly (6 or more attributed events) by a closed group of 2–3 agents, where most events are not task-API calls. It first fires on **2026-07-09 19:20 UTC**:
  - **14.3 h** before the Hugging Face credentials were found,
  - **44.7 h** before the RCE on the Hugging Face worker,
  - about **63 days** before public discovery.

  The *board* signal fires at 2026-07-09 00:00 UTC. This is about 1 h after METR's documented board start, so the tool independently recovers that milestone. But the board signal is accurate only to the day, and it depends on knowing the swarm's message format.
- **Synthetic sanity check.** We plant one colluding pair in a fake log with 20 agents (`tests/test_synthetic.py`, 100 seeds). Results: private-channel recall 100%, early fires 0%, false alarms 0%, and the planted pair ranks first 100% of the time. This test is easy on purpose. Section 9 lists harder ones.

## 7. What an investigator would still miss

1. **Unsigned agents.** About 99% of events have no provable author. Coordination between agents that never signed their work is not visible in the graph.
2. **Aliases.** Agents choose their own names. The source report found about 7,905 names for about 700 agents. Our alias detector finds only names with the same stem, for example `URI23816C` and `URI23816D`.
3. **Time.** The estimated order is only a rough proxy. The dated subset (3,780 events) may not represent the whole swarm.
4. **One-sided capture.** Most responses are missing, so we often cannot confirm that a payload actually ran.
5. **Content of encrypted channels.** We can see that a signed or encrypted channel exists. We cannot see what it carried.
6. **Intent.** The graph shows structure, not intent. A parallel coincidence can look like coordination. Every alert is a lead for a human to check, not a verdict.
7. **Direction through dead-drops.** We infer "write then read" from order. We cannot prove that agent B read what agent A wrote.
8. **False-alarm rate on real logs is not measured yet.** Synthetic tests are not enough. We need a real benign control log (AI Village).

## 8. How this connects to the readings

| Reading | What we take from it |
|---|---|
| Hammond et al. 2025, *Multi-Agent Risks* | Their taxonomy (miscoordination, conflict, collusion) tells us what to label. Today our detectors cover the *collusion* signals. |
| Motwani et al. 2024, *Secret Collusion* | Steganography and covert channels lead to our covert-channel inventory. Hidden *content* inside text is out of scope for v1. |
| Rose et al. 2026, *Detecting collusion via interpretability* | They use the models' internals. We use the logs only. The two approaches complement each other. |
| Greenblatt et al. 2024, *AI Control* | Our early-warning replay is a trusted-monitoring setup: online, with past data only, and measured by lead time. |
| Zhang et al. 2025, *Attributing failures* | Attribution of actions to agents is our hardest problem in de-identified logs (aliases, unsigned agents). |
| Tomašev et al. 2025, *Distributional AGI Safety* | Capability can come from the network, not from one agent. That is why the unit of analysis is the graph. |

## 9. Next steps (in priority order)

1. **AI Village as the control log.** Accept the terms, download `swarm-village` (~100 MB), and run the tool. Measure how often each signal fires on a mostly benign swarm. This gives us our first real false-alarm rate. First check the loader's field names against `SCHEMA.md`.
2. **Harder synthetic tests.**
   - Plants at a lower rate.
   - Plants that hide inside popular resources.
   - Plants that rotate aliases.
   - Groups larger than 3 agents.

   Report recall, false alarms and delay for each case.
3. **Ablations.** Remove one part at a time and measure the change in lead time and in ranking. The parts are: the task-API filter, Adamic–Adar, and the estimated order versus file order.
4. **Better time recovery.** Use the decode chains and shortener-code continuity to place undated events between dated ones.
5. **Alias merging.** Merge handles by behaviour (same resources, same mechanisms), not only by name stem.
6. **Information-spread view in the viewer.** Pick a credential or dataset and animate its cascade.
7. **Deploy.** Publish the viewer as a hosted page. Later, a small upload page: drop in a JSONL log, map its fields, and get the viewer back.

## 10. Risks

- **The early-warning numbers depend on a small dated subset.** We report this clearly, and we do not claim a clock time for undated events.
- **The keyword flags can be noisy.** For example, the `signed_cmd` flag matches the word "signature". So we keep these flags out of the alert rule, and we report them as non-specific.
- **Dual use.** The tool describes attack mechanisms at the level of categories only. It never prints payload text. Reports show only IDs, counts and flags.

## 11. How to run

```bash
# Swarm Traces (about 1 minute)
python -m swarmscope.cli analyze Swarm-Traces-Data/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces

# AI Village (after the download script)
python -m swarmscope.cli analyze data/ai-village/swarm-village \
    --format ai_village --out outputs/ai_village_swarm-village

# Any JSONL log
python -m swarmscope.cli analyze my_log.jsonl --format generic \
    --map actor=from,channel=thread,text=body,ts=time --out outputs/mine

# Tests
python tests/test_synthetic.py && python tests/test_loaders.py
```

The package needs Python 3.9 or later and uses only the standard library. To download AI Village, you also need `huggingface_hub`.
