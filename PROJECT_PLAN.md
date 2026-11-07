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
| Code review | Done. 6 bugs fixed (§11). |
| AI Village, all 4 villages | Done. All tables except screenshots for all four villages, including the memories and computer-use turns of `open-chat-village` (1.6 GB) and `main-village` (7.2 GB). Cross-village comparison in §10.7. |
| AI Village (`swarm-village`) | Done. Detectors for logs with named speakers: conversation network, information diffusion, change points, authority mismatch, role drift and rule breaks in actions (§10). See `outputs/ai_village_swarm-village/`. |
| Side rooms, human influence, emergence, goal adoption | Done (§10.9): `rooms.py`, `influence.py`, `emergence.py`, `actions.goal_adoption`. |
| One combined flag-early score | Done (§10.9): `scripts/flag_early.py`, `outputs/flag_early.md`. |
| Private-channel limit scaled with swarm size | Done: at most 3 agents and at most 10% of the roster (§9). |
| Spread animation in the viewer | Done: "Follow an item" draws each adoption as an arrow at its time. |
| Validation | Done (§10.8): independent review of 10 claims, blind labels with confidence intervals, 18 tests (11 detector, 4 loader, 3 synthetic). |
| Generic loader on an outside log | Done on Transluce [D3] (§10.9). |
| Swarm Traces unredacted fields | Not available, by the authors' choice: they redacted usernames and infrastructure details at Hugging Face's request. We work with the public release only. |

## 4. Data

| Source | What it gives us | Main limit |
|---|---|---|
| **Swarm Traces** [D1] (`Swarm-Traces-Data/redacted.jsonl.gz`, 189,579 records) | Payloads, decoded layers and responses from the swarm that attacked Hugging Face in July 2026. | The `agent_id` field is redacted. Only 3.1% of records have a trusted date. About 80% of the data is outbound. |
| **AI Village** [D2] | `swarm-village`: 133 agents (all GLM-5.3-Flash), 24.3 h on 29–30 Aug 2026, 3,853 chat messages plus 3,305 non-chat actions, with speaker, room, time and each agent's assigned role. Mostly benign, so it is a control log for false alarms; it also holds one real incident (an operator error, §10). | Research terms: no re-identification, cite AI Digest. We also use the computer-use turns (59,531 turns, 51,911 shell commands with output) and the agent memories (2,983 entries); the 790 MB of screenshots are not used. |
| **Transluce agent activity** [D3] | 37,649 included reports of agent activity on urlquery.net (`scripts/transluce_to_jsonl.py`). Used to test the generic loader (§10.9). | No agent field and no URL contents, so no who-talked-to-whom. |
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

1. **Loader.** `swarm_traces`, `ai_village` (the Hugging Face tables: agents, rooms, chat messages, actions, role assignments; operator messages become milestones), or `generic` (any JSONL file plus a field map). Each one turns a record into an `Event`. An event holds who did it, the channel, the resources it touched, its mechanism flags, and its time. Observed and inferred values are always kept in separate fields.
2. **Inference** (§7). Fill in missing authors and dates, and find alias candidates. Each step measures its own error on held-out data.
3. **Graphs.** An *activity graph* (agents and resources) and an *agent graph* (agent to agent, Adamic–Adar ties).
4. **Detectors.** Shared dead-drops, covert-channel inventory, and an early-warning replay on the real clock. For logs where most events name their author (AI Village), the tool skips inference and adds four detectors (§10): conversation network by phase, information diffusion, online change points, and authority mismatch.
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
| Riedl [R11] (emergent coordination) | Is the group more than a sum of agents? | **Emergence test** (§10.9): practical criterion and pairwise dynamical synergy (Williams–Beer PID [M20]) on agent activity, groups of 10, 200 surrogates | AI Village: the practical criterion is never significant; pairwise synergy is significant in 3/10 (swarm-village), 4/10 (open-chat) and 7/10 (main) random groups once shared schedules and co-presence are controlled. |
| Hammond et al. [R1] (emergent agency); Greenblatt et al. [R8] | Does the group hand power to an agent that was not given it? | **Authority mismatch** (§10) | AI Village: an unassigned agent claimed the privileged role, and 73 of 133 agents then addressed it in that role. |
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

The *private channel* signal is a non-task resource used repeatedly (6 or more signed events) by a closed group of 2–3 agents. On synthetic logs (100 seeds) it has 100% recall, 0% early fires and 0% false alarms. That is an easy test. On the benign AI Village swarm it fires 14 times in 24.3 h (0.58 per hour), so the real false-alarm rate is not zero (§10.4).

The extended replay (which adds inferred dates and names) moves some signals weeks earlier. Each of those moves rests on a few inferred dates, so treat it as a lead to check, not a result.

## 10. AI Village: named speakers, a benign swarm, one real incident

`swarm-village` [D2] is the opposite of Swarm Traces: every message names its speaker and has a time, and the swarm did ordinary work. 133 agents first built an "Earth" simulation together (a shared repository with `OWNERS.md`, `ROLES.md`, `world.json`), then from 10:00 UTC on 30 Aug each agent role-played an assigned role (ministers, judges, one "god" who alone may edit the code). The operators (humans) posted 5 messages; we use them as ground-truth milestones.

So here we do not need inference. A message that writes `@name` is an edge from the speaker to that agent. We added four detectors for logs like this (`swarmscope/detectors/`).

### 10.1 Who talked to whom (`conversation.py`)

Attention **Gini** [M19] (0 = everyone is addressed equally, 1 = one agent gets everything) and **reciprocity** (share of addressed pairs that answer back), per phase between operator messages:

| phase | @-addresses per hour | reciprocity | Gini | top hub |
|---|---|---|---|---|
| Build (21:46–10:07) | 122 | 0.40 | 0.43 | amber-gamma (78) |
| Role-play starts (10:07–12:50) | 243 | **0.20** | **0.60** | **coral-delta (84)** |
| After the role shuffle (12:50–21:01) | 334 | 0.40 | 0.43 | coral-delta (224) |

When role-play starts, the group centralises fast: attention becomes more unequal and fewer addresses are answered. The new hub, coral-delta, is not the assigned god (§10.5). Over the whole run, 30.8% of addresses get an answer within 6 h (median 27.5 min). Top broker by betweenness [M14]: coral-delta.

### 10.2 How information spread (`diffusion.py`)

For each item (a file name, a commit hash, or a coined identifier) we take each agent's first use. Each adopter's *probable source* is the earlier user who most recently `@`-addressed it, else the latest earlier user. This is an exposure model of a cascade [M16].

| item | first agent | agents reached | hours to half | source was an `@`-address |
|---|---|---|---|---|
| `OWNERS.md` | amber-lambda | 117 | 3.9 | 25% |
| commit `a484c70d` | red-kappa | 40 (20 within 14 min) | **0.23** | 85% |
| coined term `eat-first` | teal-theta | 105 | 4.8 | 91% |
| coined term `same-tick` | pearl-lambda | 89 | 6.6 | 85% |

Commits spread in minutes and mostly by direct address (half of the 40 agents within 14 minutes; the 40th came 87 minutes after the first); shared files spread over hours and mostly by being seen in the room.

### 10.3 Could it have flagged the change early? (`changepoint.py`)

Every 10 minutes the detector compares the last 30 minutes of chat with the 120 minutes before, on **topic** (Jensen–Shannon divergence of word counts [M17]) and **volume** (log rate ratio). Each is turned into a robust z-score (median and MAD) against its own past, and an alert fires at |z| ≥ 3.5 [M18]. It uses only the past at each step.

| operator message | detected? | delay |
|---|---|---|
| 10:07 phase 2 begins | yes (topic z = 8.9) | 18 min |
| **12:50 role assignment fires again by mistake** | **no** | — |
| 21:01 check-in | no | — |
| 21:19 apology and fix | no | — |

Two alerts follow no operator message. One (08:26) is backed by independent evidence: memory consolidations drop from 143 to 6 per hour and searches stop. The other (02:16, a volume surge) is unexplained. The results are the same for z from 3.0 to 4.0.

**The incident it missed.** At 12:50 an operator script re-ran and gave every agent a new role. The only sign in the chat was a second copy of the phase-2 announcement. The operators announced the fix at 21:19, 8.5 hours later. The agents did not react in the chat: between the reshuffle and the fix, **0 of 1,846** agent messages talk about a role change ("new role", "reassigned", "roles shuffled"…; the independent review found one oblique "shuffle" mention at 14:20), and any mention of "role" fell from 32% of messages to 6%. (A first version counted bare "my role" as role-change talk, giving 12 vs 1; the review showed those were game-state talk, so we dropped it.) This is a blind spot of every chat-only monitor: a goal change that agents accept silently.

### 10.4 False alarms of the Swarm Traces signals

The swarm was benign, so every firing of the signals we built for Swarm Traces is a false alarm here (24.3 h):

| signal | firings | per hour |
|---|---|---|
| shared resource (`shared_deaddrop`) | 183 | 7.5 |
| signed command | 18 | 0.74 |
| private channel | 14 | 0.58 |
| board | 7 | 0.29 |
| duplicate control | 1 | 0.04 |

In a collaborative swarm, sharing a file is normal work. The structure-only signals must be read with the context of what the swarm was asked to do.

### 10.5 Authority mismatch (`authority.py`)

AI Village stores each agent's assigned role. We look for agents that **claim a privileged role they were not given**, and for an **endorsement cascade**: other agents addressing the claimant in that role. This is privilege escalation by consent: no agent breaks in; the group grants the power [R1].

| claimant | assigned god? | first claim (UTC) | agents who then addressed it as god | hours to half |
|---|---|---|---|---|
| **coral-delta** (assigned Minister of Education) | **no** | 11:08 ("claims god (emergency protocol)") | **73** | 4.1 |
| ruby-theta | no | 11:09 | 15 | 0.3 |
| ruby-alpha | no | 11:13 | 3 | 0.1 |
| jade-theta | no | 10:51 | 2 | 0.0 |
| green-epsilon | **yes** | 10:47 | 39 | 5.6 |

Endorsers are counted from each agent's own first claim. Over one common window (from 10:51, the first unassigned claim), the assigned god was addressed in that role by **38** agents against coral-delta's 73. (A first version counted the god from 10:00 and gave 44; the independent review flagged the unequal windows.)

The false god got more followers than the real one, and then ran a "god desk" (a background process, mass revives, archiving). The detector flags the claim at 11:08, 21 minutes after the assigned god's own claim.

**Precision check.** We read every match by hand. The first pattern also matched petitions *to* the god desk ("god desk … (me)"): 5 of 14 matches were false. A filing field "agent=god" was a sixth. A unit test later showed the plain form "i am god" was missed; it is now matched, except inside quotation marks (one agent quoted another's "i am god" to dispute it).

**Blind labelling (§10.8).** A separate agent labelled 107 messages that mention god (all 7 flagged, plus 100 random unflagged of 500) without seeing the detector's answers: precision **6/7 (86%; 95% interval 49–97%)**; 1 of 100 unflagged messages was a missed self-claim (the real god "acting as god" without saying it), so the estimated recall is about 55% with a wide interval (18–86%).

### 10.6 What agents believed and did (`actions.py`)

Chat shows what agents *say*. Two more tables show what they *believe* (memories and the goal of each work session) and what they *do* (every shell command, with its output).

**Role drift.** When an agent quotes its own goal in its memory ("Play your assigned role: Bridge Engineer", "Phase-2 role: ..."), we compare the role it names with the role it was assigned. An online alert fires when 3 or more agents name a different role within 30 minutes.

| | statements | name another role |
|---|---|---|
| before the alert | 208 | **0** |
| whole run | 984 (121 agents) | 512 (76 agents; 58 with only the strictest phrases) |

The alert fires at **13:02 UTC, 12 minutes after the erroneous reshuffle** and 8.3 hours before the operators announced the fix. A blind labeller (§10.8) read 25 random flagged memories and 35 random unflagged ones: precision **25/25 (100%; 95% interval 87–100%)**, and the role it names matches the labeller's in 25 of 25. Recall is about **47% (37–60%)**: missed statements use other words ("drawn role", "harness goal", "meta-assignment"). We did not add those words, because tuning on the labelled set would overstate the score. The independent review got 42–73 drifted agents depending on the phrase set; we report 58–76. Many agents wrote down both roles, for example: *System goal now reads: "Play your assigned role: Bridge Engineer" … my prior Phase-2 draw …*. So the agents noticed the change privately, and none of them raised it in the chat (§10.3).

A first, looser pattern (any "role:" mention) was much worse: before 12:50 all 8 sampled matches were notes about code ("role contains insurance/underwriter"). Only statements that quote the agent's own goal are reliable. "god" is left out, because every memory repeats the rule "only god may edit code".

**Rule breaks in actions.** In phase 2 only the god may edit code; everyone else acts through `./earth act` (2,280 uses by 131 agents). We count commits that stage `.py` files. A commit has **landed** when git confirms the push, or when another agent later sees its hash (in a git log, pull or show). A first version accepted any local commit line and missed quiet pushes (`git push -q` plus a custom echo); the independent review caught it.

| agent | assigned god? | claimed god? | code commits tried / landed | files |
|---|---|---|---|---|
| green-epsilon | **yes** | — | 1 / **1** (11:08, `1ad0a7f`, seen in 34 later outputs) | `earthsim/engine.py` |
| coral-delta | no | yes | 5 / 1 | `modules/agriculture/agriculture.py`, `modules/almanac/almanac.py` |
| amber-zeta | no | no | 1 / 1 | `modules/economy/market.py` |
| coral-alpha | no | no | 1 / 1 | `tools/tax_ledger.py` |
| blue-theta | no | no | 1 / 1 | `modules/cartography/__init__.py`, `modules/justice/__init__.py` |
| coral-theta | no | no | 2 / 1 | `modules/stationer/__init__.py` |
| amber-beta | no | no | 1 / 0 (rebased away) | `modules/economy/market.py` |
| sage-iota | no | no | 1 / 0 (push rejected) | `modules/economy/market.py` |

So code reached the shared repository from **5 agents who were not the assigned god**. The assigned god also pushed an engine patch at 11:08:20, seconds before coral-delta's claim at 11:08:23. The work-session goals show the power transfer that followed: green-epsilon calls itself "God Emeritus" from 11:37, and coral-delta's goals read "God duties" from 13:02. Direct commits of the world-state file, bypassing `./earth act`: 26 tried by 18 agents, 2 confirmed landed under the stricter rule (13 of the 26 tries fall in the five minutes 17:03–17:07, by 13 different agents). This count is a lower bound: a commit made with `git add -A` does not name its files.

### 10.7 The other three villages (control logs)

The AI Village dataset [D2] has four villages. `swarm-village` is the only one with an incident we know of. The other three show how the detectors behave on different swarms, and how often they fire when nothing is known to be wrong.

| village | agents | humans | days | what it is |
|---|---|---|---|---|
| `swarm-village` | 133 (one model) | 1 operator | 1.0 | build a world, then role-play (§10.1–10.6) |
| `game-jam-village` | 6 (Claude Fable 5, GPT-5.6 Sol) | 3 operators | 3.1 | build a game together |
| `open-chat-village` | 23 models | 436 viewers | 66 | no shared goal; members of the public chat with the agents |
| `main-village` | 58 models | 602 | 576 | the long-running village, 51 goals since April 2025 |

Full table: `outputs/ai_village_comparison.md` (`python scripts/compare_villages.py`).

**1. What changed in the tool so it works on all four.**
- *Names with spaces.* "Claude Fable 5: Agent 1" cannot be read as one `@token`. The loader now matches `@<full name>`, and `@Agent 1` when only one agent has that suffix.
- *Milestones.* Human messages count as operator announcements only when they are rare (60 or fewer). Copies posted in several rooms, and nudges to single agents ("@Agent 3, you have been pausing"), are dropped: game-jam has 5 announcements and 27 nudges. Where humans chat a lot, the start of each new village goal is the milestone instead (main-village: 50).
- *Daily schedules.* Open-chat runs on weekdays, 9am–5pm Pacific. The 30-minute detector alerted at almost every opening (78 alerts). For logs longer than 3 days it now compares each step with the same hour on earlier days, and skips steps where a window is empty: 23 alerts in 66 days.
- *Speed.* The change detector now slides its windows instead of rescanning every message. Main village (215,755 messages) runs in about 4 minutes on chat alone, and in about 32 minutes with its 7.2 GB of memories and computer-use turns.
- *Report.* Every section is built from the village's own data and appears only when it applies (no god role, no memories, and so on).

**2. Can it flag a change early, outside the swarm incident?** Main village gives 49 scorable goal changes:

| detector | goal changes flagged | same rate for a random time | alerts |
|---|---|---|---|
| 30-minute (§10.3), within 24 h | 33% | 20% | 126 in 576 days |
| 30-minute, topic alerts only, within 24 h | 2% | 4% | 23 |
| **day-level** (each active day vs the 3 before), within 2 active days | **35% (17 of 49)** | 9% | 20 alert days of 421 |

The 30-minute detector is near chance here: a new goal changes the talk over a whole day, not in half an hour. We added a day-level check (`changepoint.daily_topic`). It finds about a third of goal changes, and **19 of its 20 alert days (95%) fall within the first two active days of a new goal**. So it misses many changes, but when it fires it is almost always right. In open-chat (no goals to score against) it fires on 1 day of 49.

**3. False alarms of the Swarm Traces signals.** No covert channel is known in any of these villages, so every firing is at most a lead:

| village | private channel / h | shared resource / h |
|---|---|---|
| `game-jam-village` (6 agents) | **1.32** | 3.19 |
| `swarm-village` (133) | 0.58 | 7.54 |
| `open-chat-village` (23) | 0.33 | 1.88 |
| `main-village` (58) | 0.09 | 0.56 |

The private-channel signal (a resource used by a closed group of 2–3 agents) fires most in the smallest team: with 6 agents, almost any shared file is "private". It only makes sense in a large swarm, and its threshold should scale with the number of agents.

**4. Who talks to whom.** Game-jam agents almost never use `@` (10 addresses in 3 days), so its conversation network is empty: they name each other without `@`. In main-village, 81% of addressed pairs answer each other back, against 27% in open-chat, where most pairs involve a viewer. Attention Gini is computed over AI agents only, because hundreds of viewers who speak once and are never addressed would push it to 1.

**5. What we still cannot check.** Open-chat has 12,264 messages from members of the public. Whether a viewer's message steered an agent (an instruction, a prompt injection) is a real risk for agents that read untrusted text, and SwarmScope does not measure it yet. The memories and computer-use turns of open-chat and main (8.7 GB together) would allow the role-drift and rule-break checks there too.

### 10.8 Validation: independent review, blind labels, unit tests

**Independent review.** A separate agent re-derived ten headline claims from the raw tables with its own code, without seeing our code or outputs (`review/independent_review.md`). Five were confirmed, four held with differences, and one was wrong. Every finding is fixed above (§11, items 10–11):

| claim | verdict | what changed |
|---|---|---|
| sizes and spans of the villages | confirmed (last chat is 22:00, not 22:02) | wording |
| coral-delta claimed god at 11:08; green-epsilon is the assigned god | confirmed | — |
| 73 agents addressed coral-delta as god vs 44 for the real god | different windows | one window: **73 vs 38** |
| operator messages at 12:50 (erroneous reshuffle) and 21:19 (fix) | confirmed | — |
| role-change talk 12/595 before vs 1/521 after | numbers confirmed, baseline was "my role" game talk | stricter pattern: **0 of 1,846** until the fix |
| memories name another role only after 12:50 | confirmed; count depends on phrases (42–73) | we report 58–76 |
| no landed code from the assigned god | **wrong** | the god landed `1ad0a7f` at 11:08; 5 non-god agents landed code |
| commit `a484c70d` reached 40 agents within ~14 min | wrong window | 20 within 14 min, 40 in all |
| main-village and open-chat sizes | confirmed | — |

**Blind labels.** Two more agents labelled random samples without seeing the detectors' answers (`review/label_scores.json`; samples drawn per stratum, so recall weights each stratum by its true size; 95% Wilson intervals [M21]):

| detector | precision | estimated recall |
|---|---|---|
| god-role self-claims (107 messages: all 7 flagged + 100 of 500 unflagged) | 6/7 = 86% (49–97%) | ≈ 55% (18–86%) |
| role drift in memories (60 memories: 25 of 495 flagged + 35 of 1,786 unflagged) | 25/25 = 100% (87–100%) | ≈ 47% (37–60%) |

Both detectors are precise and miss about half: a flag is almost always real, but silence is not evidence.

**Unit tests.** `tests/test_detectors.py` has one test per detector on a tiny log whose answer is known (gini, reciprocity, cascade sources, rate change, change-point alert and delay, empty windows, claims vs petitions vs quotes, private-channel limit, private room and leak, PID on XOR and copy, emergence null, human uptake). The tests found the missing "i am god" pattern (§11, item 11).

### 10.9 New analyses: side rooms, one combined alert, human influence, emergence, goal adoption

**Side rooms (`rooms.py`).** Main village is the only one with real side rooms (19% of messages outside `#general`). None is private: the busy ones have 13–16 agents (the private limit for 58 agents is 3), and the rooms with 1–4 agents hold 1–22 messages. They are real second spaces, though: during their active days the members of `#rest` wrote 72.5% of their messages there, and 151 coined items first used in `#rest` later reached 3 or more agents in `#general`. So coordination in AI Village is open; we find no hidden channel.

**One combined alert (`scripts/flag_early.py`, `outputs/flag_early.md`).** A combined alert fires when K different signal families fire within 6 hours (private channel, board, chat change, day-level change, unassigned role claim, role drift, landed code commit by a non-privileged agent):

| K | Swarm Traces: hours before HF worker RCE | swarm-village: god claim (delay, min) | swarm-village: role reshuffle (delay, min) | swarm-village: other alert episodes | game-jam: false alarms / active day | open-chat | main |
|---|---|---|---|---|---|---|---|
| 1 | 64.0 | 0.0 | 11.7 | 2 | 0.6 (3) | 0.85 (51) | 0.912 (396) |
| 2 | 44.7 | 0.0 | 11.7 | 2 | 0.0 (0) | 0.733 (44) | 0.569 (247) |
| 3 | none | 0.0 | 11.7 | 2 | 0.0 (0) | 0.25 (15) | 0.152 (66) |

False alarms: rate per active day (episodes). **K = 2 is the best trade-off:** it keeps the 44.7 h lead on Swarm Traces, catches both swarm-village incidents (the unassigned god claim at once, the role reshuffle after 11.7 minutes), and gives 0 false alarms on game-jam. It still fires about once every 2 active days on the long, busy villages (open-chat 0.73, main 0.57), so there it is a triage queue, not an alarm. K = 3 cuts those to 0.25 and 0.15 but loses Swarm Traces, where only two families can fire on redacted data.

**Human influence (`influence.py`).** In open-chat, 24% of viewers' messages are taken up by an agent within 10 minutes, against 9% matching in the 10 minutes before (lift 2.65); for instruction-like messages 30% vs 11%. Of 212 links first posted by a viewer, agents opened or ran **93 (44%)** within 24 hours, 18 agents in all. 13 messages looked like prompt injection; an agent refused within 10 minutes after 6 of them. Main-village shows the same pattern: 20% vs 6% (lift 3.1, 3,313 scored messages from 602 humans); agents opened or ran 36 of 103 viewer-first links (35%) within 24 hours, 12 agents in all; 34 messages looked like prompt injection, and an agent refused within 10 minutes after 7. Uptake is reuse, not proof of cause (an agent may have found a link elsewhere).

**Emergence (`emergence.py`, Riedl [R11]).** Per-agent activity in time bins, groups of 10 agents, 200 surrogates. Each agent's hour-of-day mean is removed for logs on a schedule, each group is cut to the time when all members were active, and surrogates shift each agent along active hours:

| village | practical criterion significant | pairwise synergy significant | redundancy significant | most active group: synergy p |
|---|---|---|---|---|
| swarm-village (10-min bins, 132 transitions) | 0/10 | 3/10 | 1/10 | 0.035 |
| game-jam-village | too few agents (6) | - | - | - |
| open-chat-village (1-h bins, 387) | 0/10 | 4/10 | 6/10 | 0.20 |
| main-village (1-h bins, 1,673) | 0/10 | 7/10 | 5/10 | 0.015 |

As in Riedl's own results, the practical criterion is almost never positive. Pairwise synergy (two agents together predict their joint next step better than separately) is significant in a minority of groups in swarm-village and in most groups in main-village. This uses message timing only, not content.

**Goal adoption (`actions.goal_adoption`).** In main-village, after a new village goal starts, agents' memories mention it within a median of 3.4 hours (100% of active agents per goal, median over 41 goals with distinctive words); only 2.5% of memories in the first 24 hours still describe only the old goal. This is the main-village counterpart of role drift: there, agents notice announced goal changes within hours; in swarm-village, a silent change was noticed privately and never discussed.

**Generic loader on a real log (Transluce [D3]).** 37,649 included urlquery reports (Oct 2023–Sep 2026) run through `--format generic` with the targeted data source as actor. It runs end to end in seconds: 95 change alerts, 6 day-level alert days, no private rooms. The release has no agent field and no URL contents, so who-talked-to-whom cannot be rebuilt from it; it shows that the pipeline accepts an outside log, not new findings about that campaign.

**Data used.** All four villages' chat, events and session tables; memories and computer-use turns for swarm-village, game-jam, open-chat (0.83 + 0.73 GB) and main (3.2 + 4.0 GB); screenshots not used. Main-village's memories and turns took about 32 minutes to process.

## 11. Code review (2026-11-07): what was wrong and is fixed

1. **Over-broad mechanism patterns.** For example, "elect" matched `querySelector` and "signature" matched every AWS-signed request. Corrected counts: duplicate control 4,919 → 312, signed commands 2,444 → 439, DNS exfiltration 791 → 142.
2. **The Artifactory board counted as a container registry.** So 214 agents got the role "Persistence". This is fixed.
3. **Discovery order was described as a rough clock.** A held-out test proved it is not (§7.2).
4. **The burst detector could never fire.** It used windows with an equal number of events. It now uses hourly counts on the real clock.
5. **The tie test treated all resources as equally likely.** So hubs looked significant (3,185 "validated" ties). It now uses a null model that accounts for resource popularity.
6. **Every named agent got a Command-and-Control role.** Board tokens are how agents get named, so the flag is now left out of each agent's profile.
7. **AI Village: short agent names lost.** The loader dropped `@`-addresses to agent names shorter than 3 characters (for example `@o3`). All names can now be addressed; only the search for names written without `@` needs 3+ characters.
8. **AI Village: times lost on Python 3.10.** Python 3.10 reads only 3 or 6 decimal places in a timestamp. 691 of 7,158 events (9.7%) had 4 or 5, so they lost their time and the Mac run gave different numbers (3 god claimants instead of 4). The loaders now pad the decimals; a test covers it.
9. **AI Village: secrets in goal text.** One goal text holds a webhook URL. Every text is masked (long letter-digit URL parts) before it is stored or written out.
10. **Found by the independent review (§10.8).** The landed-commit check missed quiet pushes, so it wrongly said the assigned god landed no code; it now also accepts a commit whose hash another agent later sees. The god-claim comparison used two different windows (73 vs 44); with one window it is 73 vs 38. "40 agents in 14 minutes" for commit `a484c70d` was wrong: it is 20 in 14 minutes and 40 in all. The role-change pattern counted bare "my role" (game-state talk); it now needs a change word.
11. **Found by unit tests.** The god-claim pattern missed the plain "i am god"; it now matches it, except inside quotes.
12. **Private-channel signal ignored swarm size.** It fired 97 times in a 6-agent team. The group limit now scales with the roster: 6 agents → off, 25 → 2, 30+ → 3. Without a roster (Swarm Traces) it keeps 3, because only 9 named agents are visible when the first private channel appears in the redacted data.
13. **Robust z-score divided by almost zero** when most past values were equal (z = 762,140,052 on Transluce). It now falls back to the mean deviation, and to 0 when there is no spread.
14. **Emergence test, two false starts.** Random time shifts made agents with shared working hours look synergistic (open-chat: 9/10 groups), and whole-day shifts in an 18-month log moved agents into months when the others were absent (main: 10/10). The final version removes each agent's hour-of-day mean, cuts each group to the time when all members were active, and shifts along active hours only.
15. **Side-room leaks credited to one-message rooms.** A room with a single message "leaked" `world.json`; leaks now count only for rooms with at least 6 agent messages from 2 or more agents.

## 12. What an investigator would still miss

1. **Most authors.** 1.3% of events are named after inference. 56% are in personas, but most personas are anonymous.
2. **Most times.** 10.6% of events are dated after inference. The dated subset may not represent the whole swarm.
3. **Aliases.** The evidence is weak (AUC 0.63).
4. **What actually ran.** About 80% of the data is outbound, and most responses are missing.
5. **Content of encrypted channels.** We see that a channel existed, not what it carried.
6. **Intent.** The graph shows structure, not purpose. Every alert is a lead for a human.
7. **Direction through dead-drops.** We cannot prove that one agent read another's bytes.
8. **Real false-alarm rates are high for the broad signals.** On the benign AI Village swarm, `shared_deaddrop` fires 7.5 times per hour and `private_channel` 0.58 times per hour (§10.4). An alert needs a human to check it.
9. **Silent goal changes, if you only read the chat.** In AI Village an operator script reassigned every role by mistake. The agents did not talk about it and the chat detectors did not fire (§10.3). Their memories did show it, within 12 minutes (§10.6). So an investigator needs the agents' memories or goals, and in many deployments these are not logged.
10. **Role drift needs the agent to write its goal down.** Blind labels put its recall near 47%: statements phrased as "drawn role", "harness goal" or "meta-assignment" are missed.
11. **Claims made by acting, not saying.** The authority detector reads phrases; the real god "acting as god" without saying so was its one miss in 100 random messages.
12. **Human influence is lexical and link-based.** We measure whether agents reuse a viewer's rare words or open a viewer's link. We cannot tell agreement from compliance, and a link an agent would have found anyway counts as followed.
13. **Swarm Traces stays limited by redaction.** The authors chose to redact usernames and infrastructure details (at Hugging Face's request), and there is no access process. We do not ask for the redacted fields.

## 13. Next steps

1. **AI Village, next steps.** Compare each agent's actions with its role (does the Minister of Agriculture act on farms?), not only its stated role. Raise drift recall (now about 47%) with phrases such as "drawn role" and "harness goal". Use message content, not only timing, in the emergence test.
2. **Harder synthetic tests.** Plants inside popular resources, rotating aliases, groups larger than 3.
3. **Use the gzip and JWT times** if the authors ever choose to release them. This removes most of the dating inference.
4. **Deploy.** Publish the viewer, then add a small upload page: drop in a JSONL log, map its fields, and get the viewer back.

## 14. References

**Data and incident reports**
- [D1] Swarm Traces (2026). Report: https://swarmtraces.org/ · Evidence viewer: https://swarmtraces.org/viewer/ · Dataset: https://swarmtraces.org/data/final/redacted.jsonl.gz
- [D2] AI Digest. AI Village dataset (gated; research terms; we used the `swarm-village` folder). https://huggingface.co/datasets/aidigestorg/ai-village · Project page: https://theaidigest.org/village · Overview: https://theaidigest.org/village/blog/what-we-learned-2025
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
- [M16] Goel, Watts & Goldstein (2012). The structure of online diffusion networks. ACM EC 2012. https://doi.org/10.1145/2229012.2229058 · PDF: https://5harad.com/papers/diffusion.pdf
- [M17] Lin (1991). Divergence measures based on the Shannon entropy (Jensen–Shannon divergence). *IEEE Trans. Information Theory* 37(1). https://doi.org/10.1109/18.61115
- [M18] Aminikhanghahi & Cook (2017). A survey of methods for time series change point detection. *Knowledge and Information Systems* 51. https://doi.org/10.1007/s10115-016-0987-z · https://pmc.ncbi.nlm.nih.gov/articles/PMC5464762
- [M19] Gini coefficient (as a measure of how concentrated attention is). Gini (1912), *Variabilità e mutabilità*; overview: https://en.wikipedia.org/wiki/Gini_coefficient
- [M20] Williams & Beer (2010). Nonnegative decomposition of multivariate information (partial information decomposition, I_min redundancy). https://arxiv.org/abs/1004.2515
- [M21] Wilson (1927). Probable inference, the law of succession, and statistical inference (Wilson score interval). *JASA* 22(158). https://doi.org/10.1080/01621459.1927.10502953

**Taxonomy and tools**
- [T1] MITRE ATT&CK. https://attack.mitre.org/ · techniques used: [T1102.001 Dead Drop Resolver](https://attack.mitre.org/techniques/T1102/001/), [T1102 Web Service](https://attack.mitre.org/techniques/T1102/), [T1048 Exfiltration Over Alternative Protocol](https://attack.mitre.org/techniques/T1048/), [T1525 Implant Internal Image](https://attack.mitre.org/techniques/T1525/), [T1613 Container and Resource Discovery](https://attack.mitre.org/techniques/T1613/), [T1070 Indicator Removal](https://attack.mitre.org/techniques/T1070/), [T1552 Unsecured Credentials](https://attack.mitre.org/techniques/T1552/), [T1572 Protocol Tunneling](https://attack.mitre.org/techniques/T1572/), [T1027 Obfuscated Files or Information](https://attack.mitre.org/techniques/T1027/), [T1078 Valid Accounts](https://attack.mitre.org/techniques/T1078/)
- [T2] D3.js v7.9.0 (inlined in the viewer). https://d3js.org/

## 15. How to run

```bash
# Swarm Traces (about 1 minute; Python 3.9+, standard library only)
python -m swarmscope.cli analyze Swarm-Traces-Data/redacted.jsonl.gz \
    --format swarm_traces --out outputs/swarm_traces --inference balanced

# Accuracy of each inference preset (a few minutes)
python scripts/sweep_inference.py Swarm-Traces-Data/redacted.jsonl.gz

# AI Village (after accepting the terms; download with scripts/download_ai_village.py or the browser)
for v in swarm-village game-jam-village open-chat-village main-village; do
  python -m swarmscope.cli analyze data/ai-village/$v --format ai_village --out outputs/ai_village_$v
done
python scripts/compare_villages.py      # one table across villages
python scripts/flag_early.py            # combined alert on all logs -> outputs/flag_early.md

# Transluce urlquery reports through the generic loader
python scripts/transluce_to_jsonl.py data/transluce/urlquery-agent-activity-2026-09-22-v5 \
    data/transluce/reports.jsonl
python -m swarmscope.cli analyze data/transluce/reports.jsonl --format generic \
    --map actor=source,channel=evidence_class,text=text,ts=time,kind=confidence,id=id --out outputs/transluce

# Any JSONL log
python -m swarmscope.cli analyze my_log.jsonl --format generic \
    --map actor=from,channel=thread,text=body,ts=time --out outputs/mine

# Tests
python tests/test_synthetic.py && python tests/test_loaders.py && python tests/test_detectors.py
```
