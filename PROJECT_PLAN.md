# Project plan: SwarmScope

**Apart Research hackathon, Track 4 (Multi-Agent Oversight and Control).**
Last updated: 2026-11-07. All sources are listed in [§13 References](#13-references).

## 1. Goal

SwarmScope reads multi-agent logs and shows three things:

1. **Who talked to whom.** A graph of interactions.
2. **How a piece of information spread.** A cascade over real time.
3. **Which covert channels the agents used.** For example, data drawn into the pixels of a screenshot.

The output is a **dynamic graph**. It changes over time, and each edge is one interaction. You can play the graph forward, stop it at any moment, and click a node to see what that agent did.

We also test whether the tool **could have flagged the coordination early**. Then we write down what an investigator would still miss.

## 2. Research question

> Using Swarm Traces [D1] or the AI Village transcripts [D2], can we build a tool that finds coordination, information spread, or covert channels in real multi-agent logs?

**Why it matters.** The Hugging Face swarm was found weeks after the fact [D4]. Oversight that looks at one agent at a time does not scale to 700 agents. A group-level forensic tool is something that deployers and auditors can use now.

## 3. Status (2026-11-07)

| Part | Status |
|---|---|
| Swarm Traces analysis, report, dynamic viewer | Done. See `outputs/swarm_traces/`. |
| Fixes for the 3 blind spots (authors, time, aliases) | Done. Each fix has a held-out accuracy test (§7). |
| Researcher metrics from the reading list | Done (§8). |
| Code review | Done. 6 bugs fixed (§10). |
| AI Village | **Blocked.** The dataset is gated. You must accept its terms on Hugging Face first, then run `scripts/download_ai_village.py`. |

## 4. Data

| Source | What it gives us | Main limit |
|---|---|---|
| **Swarm Traces** [D1] (`Swarm-Traces-Data/redacted.jsonl.gz`, 189,579 records) | Payloads, decoded layers and responses from the swarm that attacked Hugging Face in July 2026. | The `agent_id` field is redacted. Only 3.1% of records have a trusted date. About 80% of the data is outbound. |
| **AI Village** [D2] | Attributed chat with speaker, room and time. A mostly benign control log, which we can use to measure false alarms. | Gated. You must accept the research terms first. |
| **Transluce agent activity** [D3] | 6,467 strong-evidence reports of agent activity on urlquery.net (Mar–Sep 2026). | Not scoped yet. |
| **METR / Redwood incident report** [D4] | The timeline that we use as ground-truth milestones. | Times are approximate. |

**What the Swarm Traces authors had and we do not.** They took agent names "from both the headers they sent to servers and comments they left in their code". They dated payloads by "extracting bytes 04-07 of gzip headers, decoding JWTs, extracting Docker build times" [D1]. The public release redacts these fields (for example `[REDACTED:jwt_claim_time:…]`). So we must infer what they could read directly.

## 5. Core idea

The sender is redacted, so we reconstruct interaction through **shared resources**. If two agents used the same dataset, mailbox or credential, they interacted through it. This is called a **dead-drop**.

A small example with real numbers:

- `destination:000002` appears in 5,666 records and is used by 70 named agents. Every agent was *given* this endpoint, so sharing it says little.
- `destination:002666` is used by only 16 named agents, and only 1% of its records are task traffic. Sharing it says much more.

The tool weights each shared resource by its rarity: a resource used by k agents adds `1/log(1+k)`. This is the **Adamic–Adar** score [M1].

## 6. Pipeline

```
log ─► loader ─► events ─► inference (authors, dates, aliases) ─► graphs ─► detectors + researcher metrics ─► report.md + findings.json + viewer.html
```

1. **Loader.** `swarm_traces`, `ai_village`, or `generic` (any JSONL file plus a field map). Each one turns a record into an `Event`. An event holds who did it, the channel, the resources it touched, its mechanism flags, and its time. Observed and inferred values are always kept in separate fields.
2. **Inference** (§7). Fill in missing authors and dates, and find alias candidates. Each step measures its own error on held-out data.
3. **Graphs.** An *activity graph* (agents and resources) and an *agent graph* (agent to agent, Adamic–Adar ties).
4. **Detectors.** Shared dead-drops, covert-channel inventory, and an early-warning replay on the real clock.
5. **Researcher metrics** (§8).
6. **Viewer.** One HTML file with a **real-clock axis** (incident week or all dates) and a **discovery-order axis** (all events, not a clock). It has play/pause, Activity and Coordination views, inferred edges drawn dashed, METR milestones on the timeline, and node details (role, tactics, leader and broker scores).

## 7. Fixing the three blind spots

The first report said an investigator would still miss three things: authors (99% unknown), time (98% unknown), and aliases. The short answer to "can we fix this?" is **partly**. The public data has redacted the fields that would fix it fully. We can *infer* some of what is missing, and we measure how often the inference is wrong. The full fix is at the source (§7.4).

### 7.1 Who wrote an unsigned event?

**Methods we looked at.**
- *Code stylometry*: identify a programmer from code style [M2].
- *Label propagation*: spread known labels over a similarity graph [M3].
- *Record linkage*: match records that agree on rare fields [M4].

**What we applied.**
1. Build an evidence graph. Two events are linked when they are in the same decode chain, or share an identifier that at most 10 events use (a proxy URL, an encoded blob, a credential).
2. Run label propagation from the signed events. A name may spread only if the agent signed at least 2 different payloads. Without this rule, one handle with a single signed event was given to 163 other events.
3. Group events into **personas**: clusters joined by identifiers that at most 4 events share.

We also tested code-template matching (a form of stylometry). It is precise only for tiny groups, because agents copied templates from each other over the board. So it has only a small weight.

**Measured result.**
- Held-out test (whole decode chains hidden, 5 folds): **precision 0.953**, coverage 0.224.
- Named events: 0.6% → **1.3%**.
- Events in personas: **56.1%**. Of these, 18.1% of all events are in personas that join 2 or more different payloads. Persona B-cubed precision is **0.994** [M5].

**Also fixed.** About half of the signed events only *mention* a board token (they read another agent's file). So each name now has a confidence: 0.8 for writes, 0.4 for mentions.

### 7.2 When did an undated event happen?

**Methods we looked at.**
- *Seriation*: order items by similarity [M6].
- *Happens-before ordering*: order events by what each one depends on [M7].
- *Monotone (isotonic) regression* from a sequence number to time [M8].

**What we applied.** Each undated event takes the weighted median time of its linked dated neighbours (4 hops, links on identifiers used by at most 25 events). Day-only dates are read as 12:00 UTC, so their error is at most 12 hours.

**Measured result** (held-out, 4,735 clock-precise anchors):
- Median error **0.01 h**. 80th percentile 2.15 h. 90th percentile 14.24 h.
- **93.7% of estimates are within 24 h.** The baseline (always guess the median time) has an 18.6 h median error.
- Dated events: 3.1% → **10.6%**.

**Negative result.** The order of redaction numbers is **not** a clock. A monotone fit from token number to time is worse than always guessing the median, for every token type we tried:
- destination: 116.7 h error vs 20.1 h baseline;
- shortener: 103.5 h vs 0.6 h;
- credential: 63.6 h vs 17.8 h.

The first version used this order as a "rough proxy for time". That claim was wrong, and every time claim now uses real dates only.

**Presets** (`--inference precise|balanced|broad`; reproduce with `scripts/sweep_inference.py`):

| preset | names: precision | names: coverage | events named | dates: median err (h) | p80 (h) | p90 (h) | within 24 h | events dated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| precise | 0.953 | 0.224 | 1.3% | 0.0 | 0.78 | 4.33 | 96.8% | 4.7% |
| balanced (default) | 0.953 | 0.224 | 1.3% | 0.01 | 2.15 | 14.24 | 93.7% | 10.6% |
| broad | 0.83 | 0.313 | 6.5% | 0.01 | 2.77 | 21.07 | 93.0% | 15.8% |

### 7.3 Which handles are one agent?

**Methods we looked at.**
- *Record linkage* [M4].
- *Sybil detection* in social networks: one actor, many accounts [M9].

**What we applied.** We score each pair of handles by the **personal** identifiers they share: one proxy URL, one whoami name, one workload ID. Each shared identifier is weighted by its rarity. Team resources do not count, because collaborators share those too.

**Measured result.** Handle pairs with the same stem (for example URI23816C / URI23816D) share a personal identifier in 15 of 36 cases, against 18.3% of random pairs. **AUC is 0.633**, so this is weak evidence.

We list 15 likely aliases, where the stem is the same *and* the pair shares a personal identifier: URI23816C=URI23816D, JFAPR05A/B/R, CDA23/P/X, and others.

Caution: many stems look like benchmark task names (LIBJXL3733, SKIA6295, GEOS33474). Two agents on the same task can share a stem without being one agent.

We also fixed one name-parsing case. `MODAL` marks work in the Modal sandbox, and it was glued to handles: `MODALBE90` is now `BE90`, a controller that the source report names.

### 7.4 What would fix this fully

- **At the deployer.** Log a stable agent ID and a timestamp on every outbound request. This is the "agent identifiers" and "interaction logging" infrastructure that Chan et al. propose [R5].
- **For investigators.** With access to the unredacted data (header names, JWT and gzip times), this tool runs with far less inference. The loader and inference code do not change.

## 8. Researcher view (from the reading list)

| Reading | Question it raises | What SwarmScope reports | Result on Swarm Traces |
|---|---|---|---|
| Hammond et al. [R1] (collusion, network effects) | Is a tie between two agents more than chance? | **Statistically validated ties** [M10, M11, M12, M13] | **0 validated.** The test lacks power: signed agents use about 2 resources each (median), the best pair reaches p = 0.0017, and the bar is 3.3e-6. On synthetic data the test never gave a false tie, but it needs about 8 shared rare resources. |
| Tomašev et al. [R2] (patchwork AGI) | Did the group do more than any single agent? | **ATT&CK tactics** [T1] per agent, plus a set cover | The group covers 8 tactic groups. The best single agent covers 7. Two agents (WT8592N, GEOS33474) cover all 8. |
| Zhang et al. [R10] (who and when) | Which agent first did each step? | **Who and when** table | Mostly anonymous personas. Named authors are rare at first-move time. |
| Stackelberg attacks [R14]; mediated MARL [R13] | Who leads, who brokers? | **Leaders** (first to a shared resource, on the real clock) and **brokers** (betweenness [M14]) | Leader GEOS33474 (68 followers, median lag 10 h). Top broker AIC50. |
| Greenblatt et al. [R8] (AI Control) | How small an audit budget catches most coordination? | **Audit-budget curve** | Auditing the top 4.2% of agents covers 50% of strong ties. 19.6% of agents cover 80%. |
| Motwani et al. [R6] (secret collusion) | What hidden channels exist? | **Covert-channel inventory** | Shortener chains 37,430; image read-back 9,038; board 1,936; mailboxes 788; signed commands 439; DNS 142. |
| Riedl [R11] (emergent coordination) | Is the group more than a sum of agents? | *Planned.* Time-delayed mutual information needs a dense time series, which AI Village has. | Not run yet. |
| Rose et al. [R7] (interpretability) | — | Needs model internals. We use logs only, so the two approaches complement each other. | — |
| Foerster et al. [R12] (CaMeL for computer use) | Where does untrusted data steer actions? | The info-spread traces are a provenance view. | — |

**Information spread** (real clock):
- `credential:169` reached 14 agents in 29 hours, and half of them within 5 hours.
- `destination:000121` reached 13 agents, and half of them within 3 hours.
- The most widely used items (`credential:15`, `destination:000002`) reached 29–32 agents but over weeks, because a few uses date from May.
- 305 files were posted on the board (`zzFILE_*`).

**Bursts.** The largest burst is 2026-07-11 12:00 UTC: 2,183 events, z = 33.9, mostly Kubernetes and image read-back. It falls on the day of the RCE on the Hugging Face worker (about 16:00 UTC) [D4].

## 9. Early warning

These figures come from the strict replay: only dates and names read from the data, with an online detector.

| signal | first fires (UTC) | warning before HF credentials found | before HF worker RCE |
|---|---|---|---|
| board / mailbox | 2026-07-09 00:00 (exactly midnight: may be a date only) | 33.7 h | 64.0 h |
| **private channel** (structure only) | **2026-07-09 19:20** | **14.3 h** | **44.7 h** |
| duplicate control | 2026-07-11 (date only) | −26.3 h | 4.0 h |

Both multi-agent signals fire 63–64 days before public discovery (2026-09-11).

The *private channel* signal is a non-task resource used repeatedly (6 or more signed events) by a closed group of 2–3 agents. On synthetic logs (100 seeds) it has 100% recall, 0% early fires and 0% false alarms. That is an easy test. The real false-alarm rate needs AI Village.

The extended replay (which adds inferred dates and names) moves some signals weeks earlier. Each of those moves rests on a few inferred dates, so treat it as a lead to check, not a result.

## 10. Code review (2026-11-07): what was wrong and is fixed

1. **Over-broad mechanism patterns.** For example, "elect" matched `querySelector` and "signature" matched every AWS-signed request. Corrected counts: duplicate control 4,919 → 312, signed commands 2,444 → 439, DNS exfiltration 791 → 142.
2. **The Artifactory board counted as a container registry.** So 214 agents got the role "Persistence". This is fixed.
3. **Discovery order was described as a rough clock.** A held-out test proved it is not (§7.2).
4. **The burst detector could never fire.** It used windows with an equal number of events. It now uses hourly counts on the real clock.
5. **The tie test treated all resources as equally likely.** So hubs looked significant (3,185 "validated" ties). It now uses a null model that accounts for resource popularity.
6. **Every named agent got a Command-and-Control role.** Board tokens are how agents get named, so the flag is now left out of each agent's profile.

## 11. What an investigator would still miss

1. **Most authors.** 1.3% of events are named after inference. 56% are in personas, but most personas are anonymous.
2. **Most times.** 10.6% of events are dated after inference. The dated subset may not represent the whole swarm.
3. **Aliases.** The evidence is weak (AUC 0.63).
4. **What actually ran.** About 80% of the data is outbound, and most responses are missing.
5. **Content of encrypted channels.** We see that a channel existed, not what it carried.
6. **Intent.** The graph shows structure, not purpose. Every alert is a lead for a human.
7. **Direction through dead-drops.** We cannot prove that one agent read another's bytes.
8. **Real false-alarm rates.** These are not measured until the AI Village run.

## 12. Next steps

1. **AI Village as the control log.** Accept the terms, download `swarm-village`, and run the tool. This gives the first real false-alarm rates, and lets us add Riedl's time-delayed mutual-information test [R11].
2. **Harder synthetic tests.** Plants inside popular resources, rotating aliases, groups larger than 3.
3. **Use the gzip and JWT times** if unredacted access becomes available. This removes most of the dating inference.
4. **Deploy.** Publish the viewer, then add a small upload page: drop in a JSONL log, map its fields, and get the viewer back.

## 13. References

**Data and incident reports**
- [D1] Swarm Traces (2026). Report: https://swarmtraces.org/ · Evidence viewer: https://swarmtraces.org/viewer/ · Dataset: https://swarmtraces.org/data/final/redacted.jsonl.gz
- [D2] AI Digest. AI Village dataset (gated; research terms). https://huggingface.co/datasets/aidigestorg/ai-village
- [D3] Transluce (2026). Early rogue AI agent activity and attempts to hack found on urlquery.net. https://transluce.org/agent-activity
- [D4] METR / Redwood Research (Aug 2026). Independent investigation of the OpenAI / Hugging Face incident. https://metr.org/hugging-face-incident-report-aug-2026.pdf

**Reading list (Track 4)**
- [R1] Hammond, Chan, Clifton, et al. (2025). Multi-Agent Risks from Advanced AI. https://arxiv.org/abs/2502.14143
- [R2] Tomašev, Franklin, Jacobs, Krier, Osindero (2025). Distributional AGI Safety. https://arxiv.org/abs/2512.16856
- [R3] ARIA. Scaling Trust programme thesis. https://aria.org.uk/opportunity-spaces/trust-everything-everywhere/scaling-trust/
- [R4] Dafoe et al. (2020). Open Problems in Cooperative AI. https://arxiv.org/abs/2012.08630
- [R5] Chan et al. (2025). Infrastructure for AI Agents. https://arxiv.org/abs/2501.10114
- [R6] Motwani et al. (2024). Secret Collusion among AI Agents: Multi-Agent Deception via Steganography. NeurIPS 2024. https://proceedings.neurips.cc/paper_files/paper/2024/hash/861f7dad098aec1c3560fb7add468d41-Abstract-Conference.html
- [R7] Rose, Cullen, Abdelnabi, Torr, Kaplowitz, Schroeder de Witt (2026). Detecting Multi-Agent Collusion Through Multi-Agent Interpretability. https://arxiv.org/abs/2604.01151
- [R8] Greenblatt, Shlegeris, Sachan, Roger (2024). AI Control: Improving Safety Despite Intentional Subversion. https://arxiv.org/abs/2312.06942
- [R9] Conitzer & Oesterheld (2023). Foundations of Cooperative AI. AAAI. https://ojs.aaai.org/index.php/AAAI/article/view/26791
- [R10] Zhang et al. (2025). Which Agent Causes Task Failures and When? On Automated Failure Attribution of LLM Multi-Agent Systems. ICML 2025. https://openreview.net/forum?id=GazlTYxZss · https://arxiv.org/abs/2505.00212 · https://proceedings.mlr.press/v267/zhang25cq.html
- [R11] Riedl (2026). Emergent communication / coordination between agents. https://openreview.net/forum?id=SRn1MtMPRq. We read the arXiv version, "Emergent Coordination in Multi-Agent Language Models": https://arxiv.org/abs/2510.05174. We could not open the OpenReview page to confirm that the two are the same paper.
- [R12] Foerster, Blanchard, Nikolić, Shumailov, Zhang, Mullins, Papernot, Tramèr, Zhao (2026). CaMeLs Can Use Computers Too: System-level Security for Computer Use Agents. https://arxiv.org/abs/2601.09923
- [R13] Mediated Multi-Agent Reinforcement Learning (2023). https://arxiv.org/pdf/2306.08419.pdf
- [R14] Stackelberg Attacks on Auctions and Transaction Fee Mechanisms (2023). https://arxiv.org/abs/2305.02178
- Earlier Apart sprints: Multi-Agent Safety Hackathon, https://apartresearch.com/sprints/multi-agent-safety-hackathon-2024-09-29-to-2023-11-01 · Multi-Agent Security Research Sprint, https://apartresearch.com/sprints/multi-agent-security-research-sprint-2024-02-09-to-2024-02-11
- Related resources: dynamic-graph demo (GDM math swarm), https://jonathnchang.com/swarms/gdm-math-swarm/glmflash100-seeded-1ov-glm-120m-push-r1-20261104T042820Z/results · Multi-Agent Databank (Antimemetics Institute), https://databank.antimemetics.institute/papers

**Methods**
- [M1] Adamic & Adar (2003). Friends and neighbors on the Web. *Social Networks* 25(3). https://doi.org/10.1016/S0378-8733(03)00009-1
- [M2] Caliskan-Islam et al. (2015). De-anonymizing Programmers via Code Stylometry. USENIX Security. https://www.usenix.org/conference/usenixsecurity15/technical-sessions/presentation/caliskan-islam
- [M3] Zhu & Ghahramani (2002). Learning from labeled and unlabeled data with label propagation. CMU-CALD-02-107. https://bibbase.org/network/publication/zhu-ghahramani-learningfromlabeledandunlabeleddatawithlabelpropagation-2002 · scikit-learn implementation: https://scikit-learn.org/stable/modules/generated/sklearn.semi_supervised.LabelPropagation.html
- [M4] Fellegi & Sunter (1969). A Theory for Record Linkage. *JASA* 64(328). https://doi.org/10.1080/01621459.1969.10501049
- [M5] Bagga & Baldwin (1998). Algorithms for scoring coreference chains (B-cubed). LREC 1998 workshop on linguistic coreference. Reference scorer: https://github.com/conll/reference-coreference-scorers
- [M6] Atkins, Boman & Hendrickson (1998). A Spectral Algorithm for Seriation and the Consecutive Ones Problem. *SIAM J. Computing*. https://epubs.siam.org/doi/10.1137/S0097539795285771
- [M7] Lamport (1978). Time, clocks, and the ordering of events in a distributed system. *CACM*. https://doi.org/10.1145/359545.359563
- [M8] Isotonic regression (pool-adjacent-violators). https://scikit-learn.org/stable/modules/isotonic.html
- [M9] Cao, Sirivianos, Yang, Pregueiro (2012). Aiding the detection of fake accounts in large scale social online services (SybilRank). NSDI. https://www.usenix.org/conference/nsdi12/technical-sessions/presentation/cao
- [M10] Tumminello, Miccichè, Lillo, Piilo, Mantegna (2011). Statistically validated networks in bipartite complex systems. *PLoS ONE*. https://doi.org/10.1371/journal.pone.0017994 · https://arxiv.org/abs/1008.1414
- [M11] Neal (2014). The backbone of bipartite projections. *Social Networks* 39. https://doi.org/10.1016/j.socnet.2014.06.001 · `backbone` package (SDSM): https://arxiv.org/abs/2105.13396 · https://rdocumentation.org/packages/backbone/versions/2.1.0/topics/sdsm
- [M12] Chung & Lu (2002). Connected components in random graphs with given expected degree sequences. *Annals of Combinatorics* 6. https://doi.org/10.1007/PL00012580
- [M13] Benjamini & Hochberg (1995). Controlling the false discovery rate. *JRSS B* 57(1). https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
- [M14] Brandes (2001). A faster algorithm for betweenness centrality. *J. Mathematical Sociology* 25(2). https://doi.org/10.1080/0022250X.2001.9990249
- [M15] Raghavan, Albert & Kumara (2007). Near linear time algorithm to detect community structures (label propagation). *Phys. Rev. E* 76. https://doi.org/10.1103/PhysRevE.76.036106

**Taxonomy and tools**
- [T1] MITRE ATT&CK. https://attack.mitre.org/ · techniques used: [T1102.001 Dead Drop Resolver](https://attack.mitre.org/techniques/T1102/001/), [T1102 Web Service](https://attack.mitre.org/techniques/T1102/), [T1048 Exfiltration Over Alternative Protocol](https://attack.mitre.org/techniques/T1048/), [T1525 Implant Internal Image](https://attack.mitre.org/techniques/T1525/), [T1613 Container and Resource Discovery](https://attack.mitre.org/techniques/T1613/), [T1070 Indicator Removal](https://attack.mitre.org/techniques/T1070/), [T1552 Unsecured Credentials](https://attack.mitre.org/techniques/T1552/), [T1572 Protocol Tunneling](https://attack.mitre.org/techniques/T1572/), [T1027 Obfuscated Files or Information](https://attack.mitre.org/techniques/T1027/), [T1078 Valid Accounts](https://attack.mitre.org/techniques/T1078/)
- [T2] D3.js v7.9.0 (inlined in the viewer). https://d3js.org/

## 14. How to run

```bash
# Swarm Traces (about 1 minute; Python 3.9+, standard library only)
python -m swarmscope.cli analyze Swarm-Traces-Data/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces --inference balanced

# Accuracy of each inference preset (a few minutes)
python scripts/sweep_inference.py Swarm-Traces-Data/redacted.jsonl.gz

# AI Village (after accepting the terms and running the download script)
python -m swarmscope.cli analyze data/ai-village/swarm-village \
    --format ai_village --out outputs/ai_village_swarm-village

# Any JSONL log
python -m swarmscope.cli analyze my_log.jsonl --format generic \
    --map actor=from,channel=thread,text=body,ts=time --out outputs/mine

# Tests
python tests/test_synthetic.py && python tests/test_loaders.py
```
