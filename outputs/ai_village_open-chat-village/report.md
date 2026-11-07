# SwarmScope findings: `open-chat-village`

- Events: **110,192** (restarting_after_google_sign_in: 52, chat: 47,747, search_history: 4,106, consolidate: 34,880, pause: 23,324, request_google_sign_in: 40, outreach_approval_request: 13, outreach_approval_response: 13, request_human_helper: 8, cancel_request_for_human_helper: 6, stop_human_use_session: 3)
- Agents who spoke: **23**; chat messages: **47,747** (12,264 by humans); rooms: 1 (largest holds 100.0%); time span: **66 days** (Aug 25 20:03 to Oct 31 00:10 UTC)
- Every event names its author and has a real time, so no inference is needed. A message that writes `@name` is an edge from the speaker to that agent. Humans appear only as anonymous ids (`human:` plus 8 characters).

**No operator milestones.** Humans wrote 12,264 messages here (in this village, viewers chat with the agents), so human messages are not rare announcements and cannot serve as ground truth. Change-point alerts below are unlabelled.

## 1. Who talked to whom

`Gini` = how unequal incoming attention is (0 = equal, 1 = one agent gets all). `reciprocity` = share of addressed pairs that address each other back.

Whole log: 26,435 addresses between 1,490 pairs, reciprocity 0.272, Gini 0.324. Top hubs: DeepSeek-V3.2 (2985), Gemini 3.1 Pro (2514), GLM-5.2 (1829), DeepSeek-V4-Pro (1815). 62.1% of addresses got an answer within 6 h (median 5.9 min).

## 2. How information spread

Each item is a file name, a commit, or a coined identifier. For each agent we take its first use. `source by @` = share of adopters whose probable source had addressed them before (exposure model, Goel, Watts & Goldstein, 2012).

| kind | item | first agent | agents | hours to half | tree depth | source by @ |
| --- | --- | --- | --- | --- | --- | --- |
| file | `index.html` | Kimi K3 | 19 | 26.51 | 5 | 94.4% |
| file | `README.md` | DeepSeek-V3.2 | 17 | 307.09 | 4 | 100.0% |
| file | `rcv_count.py` | DeepSeek-V3.2 | 11 | 0.13 | 2 | 100.0% |
| file | `tally-snapshot.py` | GPT-5.6 Sol | 11 | 0.76 | 6 | 100.0% |
| file | `flag_tally.py` | GLM-5.2 | 11 | 18.5 | 5 | 100.0% |
| commit | `9500ad57` | GPT-6 Astra | 13 | 4.14 | 4 | 100.0% |
| commit | `8a9f8eb` | Claude Opus 5 | 12 | 0.03 | 2 | 100.0% |
| commit | `68dc28b` | Claude Opus 5 | 11 | 0.04 | 3 | 100.0% |
| commit | `d75859b` | Claude Opus 5 | 11 | 0.07 | 2 | 100.0% |
| commit | `c99c965` | Claude Opus 5 | 11 | 0.5 | 2 | 100.0% |
| term | `glm-5` | Claude Opus 5 | 23 | 70.37 | 4 | 90.9% |
| term | `byte-identical` | Claude Fable 5 | 19 | 121.81 | 5 | 100.0% |
| term | `server-side` | DeepSeek-V4-Pro | 19 | 280.8 | 5 | 100.0% |
| term | `read-only` | GPT-5.6 Terra | 18 | 314.23 | 5 | 100.0% |
| term | `check-in` | Claude Fable 5 | 18 | 319.01 | 5 | 94.1% |

## 3. Could it have flagged a change early?

Online change-point detector on chat: every 10 min it compares the last 30 min with the 120 min before, on topic (Jensen-Shannon divergence of word counts) and volume (log rate ratio), each turned into a robust z-score against its own past (for logs longer than 3 days: against the same hour on earlier days, so a daily schedule is not an alert). Alert at |z| >= 3.5. Steps where either window is empty are skipped.

23 alerts in all (0.35 per day): volume drop 11, topic shift 6, volume surge 6.

The 15 strongest:

| alert (UTC) | why | z topic | z volume | new words | non-chat actions changed |
| --- | --- | --- | --- | --- | --- |
| Aug 26 19:54 | volume drop | 3.42 | -6.1 | rule-book, inventory, scripts, generic | - |
| Aug 27 00:24 | topic shift | 4.45 | -1.7 | pizza, enjoy, goodbye, kick | consolidate down 40->0/h; pause down 38->0/h |
| Aug 27 16:34 | topic shift | 5.69 | 0.0 | with, snippet, label, only | pause up 24->100/h |
| Aug 27 23:04 | volume surge | -1.18 | 7.46 | eligible, reviewer, scores, scoring | - |
| Aug 28 23:24 | volume drop | -0.26 | -6.85 | america, los_angeles, timezone, corrections | consolidate down 47->6/h |
| Aug 31 16:34 | volume surge | 0.0 | 4.57 | ballot, your, kimi, deepseek-v | consolidate up 9->28/h; pause up 22->126/h |
| Sep 01 00:14 | topic shift | 4.05 | -0.44 | nonce, bedtime, protocol, visiting | consolidate down 24->0/h; pause down 60->0/h |
| Sep 04 23:34 | volume drop | 0.0 | -5.1 | weekend-ready, stale, size, tallies | - |
| Sep 07 18:14 | volume drop | 0.0 | -7.58 | account, creating, email, google | consolidate down 12->2/h |
| Sep 10 21:54 | volume drop | 1.82 | -3.91 | secret, index-coqr, nominal, minutes | - |
| Sep 11 23:44 | volume surge | 0.71 | 3.96 | meow, challenge, agents, merged | search_history up 6->26/h; pause down 64->16/h |
| Sep 17 19:54 | volume drop | 0.0 | -4.44 | card, metric, becomes, modern | - |
| Sep 18 22:04 | volume surge | 0.65 | 4.78 | true, memory, consolidation, loop | - |
| Sep 30 23:14 | volume surge | 1.49 | 3.93 | snapshot, today, frozen, electorate | - |
| Oct 27 22:44 | volume drop | 0.0 | -4.38 | dough, develop, fail, development | - |

**Day-level check** (for long logs). Each active day (at least 50 agent messages) is compared with the 3 active days before it; alert at z >= 2.5. 1 alert days out of 49 active days.
There are no milestones to score it against.

**False-alarm load of the Swarm Traces signals.** No covert channel is known in this village, so each firing is at best a lead for an investigator:

| signal | firings | per hour |
| --- | --- | --- |
| shared_deaddrop | 2986 | 1.88 |
| shared_deaddrop_nontask | 2986 | 1.88 |
| signed_cmd | 665 | 0.42 |
| private_channel | 525 | 0.33 |
| board | 363 | 0.23 |
| duplicate_control | 102 | 0.06 |

## 4. What an investigator would still miss

- **No ground truth for alerts.** Without rare operator announcements, nothing tells us which change-point alerts were real events; each one needs a human to read the chat around it.

- **Actions are missing.** Without the computer-use turns we see what agents said they did, not what they did.

- **Beliefs are missing.** Without agent memories we cannot compare what agents believe their goal is with what they were assigned.

- **Humans in the loop.** Humans wrote 12,264 messages. We do not check whether a human message steered an agent (for example an instruction from a viewer), which is a known risk for agents that read untrusted text.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

- **Mostly one room** (100.0% of messages), so there are few private side channels to find. Coordination here is open, not covert.

Data: AI Village by AI Digest (research use; see `PROJECT_PLAN.md` for terms and all sources).