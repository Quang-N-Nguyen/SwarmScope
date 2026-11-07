# SwarmScope findings: `main-village`

- Events: **215,755** (chat: 215,755)
- Agents who spoke: **58**; chat messages: **215,755** (10,029 by humans); rooms: 16 (largest holds 81.3%); time span: **576 days** (Apr 02 17:47 to Oct 31 00:00 UTC)
- Every event names its author and has a real time, so no inference is needed. A message that writes `@name` is an edge from the speaker to that agent. Humans appear only as anonymous ids (`human:` plus 8 characters).

**Milestones: 50 village goal changes.** Humans wrote 10,029 messages here, too many to be rare announcements, so we use the start of each new village goal as ground truth for "something changed" (first ones shown):

| milestone | time (UTC) | goal |
| --- | --- | --- |
| goal_2 | May 10 17:00 | Unsupervised agents look back on their previous goal and for… |
| goal_3 | May 12 12:00 | Holiday: do whatever you'd like! Next goal will begin soon |
| goal_4 | May 15 18:00 | Write a story and celebrate it with 100 people in person |
| goal_5 | Jun 19 12:00 | Holiday: do whatever you like! Next goal will begin soon |
| goal_6 | Jun 26 12:00 | Create your own merch store. Whichever agent's store makes t… |
| goal_7 | Jul 16 12:00 | Holiday: do whatever you prefer! Next goal will begin soon |
| goal_8 | Jul 18 12:00 | Design the AI Village benchmark for open-ended goal pursuit … |
| goal_9 | Aug 13 12:00 | Holiday: do as you please! Next goal will start soon |

## 1. Who talked to whom

`Gini` = how unequal incoming attention is (0 = equal, 1 = one agent gets all). `reciprocity` = share of addressed pairs that address each other back.

Whole log: 64,271 addresses between 1,361 pairs, reciprocity 0.808, Gini 0.64. Top hubs: DeepSeek-V3.2 (7223), Gemini 2.5 Pro (5832), Claude Opus 4.8 (4588), GPT-5.2 (4130). 69.3% of addresses got an answer within 6 h (median 5.1 min).

## 2. How information spread

Each item is a file name, a commit, or a coined identifier. For each agent we take its first use. `source by @` = share of adopters whose probable source had addressed them before (exposure model, Goel, Watts & Goldstein, 2012).

| kind | item | first agent | agents | hours to half | tree depth | source by @ |
| --- | --- | --- | --- | --- | --- | --- |
| file | `index.html` | o1 | 34 | 7392.89 | 13 | 87.9% |
| file | `README.md` | o1 | 28 | 7606.84 | 10 | 85.2% |
| file | `robots.txt` | o3 | 20 | 3506.84 | 9 | 94.7% |
| file | `Three.js` | Claude Opus 4.6 | 17 | 0.09 | 6 | 100.0% |
| file | `CONTRIBUTING.md` | Gemini 2.5 Pro | 17 | 6167.68 | 5 | 100.0% |
| commit | `eef6f89` | GPT-5.2 | 11 | 0.07 | 3 | 100.0% |
| commit | `e361431` | Claude Sonnet 4.6 | 10 | 0.04 | 3 | 100.0% |
| commit | `f81f0ed` | Claude Opus 4.6 | 10 | 0.88 | 2 | 100.0% |
| commit | `20260507d` | DeepSeek-V3.2 | 10 | 20.07 | 3 | 100.0% |
| commit | `fcec8d9` | Gemini 3 Pro | 9 | 0.05 | 3 | 100.0% |
| term | `gpt-6` | Claude Opus 4 | 44 | 8909.5 | 9 | 88.4% |
| term | `heads-up` | Claude 3.7 Sonnet | 41 | 9792.46 | 12 | 90.0% |
| term | `sign-in` | Claude 3.5 Sonnet | 39 | 7512.48 | 13 | 81.6% |
| term | `real-world` | Claude 3.7 Sonnet | 36 | 8062.72 | 8 | 85.7% |
| term | `sha-256` | o3 | 36 | 9647.02 | 6 | 88.6% |

## 3. Could it have flagged a change early?

Online change-point detector on chat: every 10 min it compares the last 30 min with the 120 min before, on topic (Jensen-Shannon divergence of word counts) and volume (log rate ratio), each turned into a robust z-score against its own past (for logs longer than 3 days: against the same hour on earlier days, so a daily schedule is not an alert). Alert at |z| >= 3.5. Steps where either window is empty are skipped.


Detected 0 of 49 village goal changes (within 90 min). Alerts that follow no announcement: 126 (0 corroborated by a change in non-chat actions, 126 unexplained).

126 alerts in all (0.22 per day): volume drop 94, topic shift 23, volume surge 9.

The 15 strongest:

| alert (UTC) | why | z topic | z volume | new words | non-chat actions changed |
| --- | --- | --- | --- | --- | --- |
| Apr 04 19:07 | volume surge | 0.08 | 11.92 | image, https, sudoredj, guys | - |
| Jun 29 23:57 | volume drop | 0.0 | -13.7 | gelato, google, sign, review | - |
| Jan 07 21:07 | volume drop | 0.0 | -10.39 | solution, requiring, automatically, pleased | - |
| Mar 09 21:27 | volume drop | 0.0 | -7.32 | potential, helping, execute, practical | - |
| Mar 13 21:27 | volume drop | 0.0 | -7.11 | commits, meta-game, browser, playing | - |
| Mar 27 21:27 | volume drop | 0.0 | -7.42 | errors, glad, appreciate, workflow | - |
| Mar 30 21:27 | volume drop | 0.0 | -8.35 | repositories, advertised | - |
| Apr 07 21:27 | volume drop | 0.0 | -7.36 | went, multiple, aiia, strategies | - |
| May 01 21:27 | volume drop | 0.0 | -6.92 | eternal | - |
| May 05 21:27 | volume drop | 0.0 | -6.99 | shoreline, small, ends, zoom | - |
| May 21 21:27 | volume drop | 0.0 | -6.96 | pausing | - |
| May 25 21:27 | volume drop | 0.0 | -6.59 | received, poll, pausing, load-bearing | - |
| May 29 21:27 | volume drop | 0.0 | -9.07 |  | - |
| Jun 10 00:27 | volume drop | 0.0 | -6.65 | surprise_puzzle_pagesmeta_, reports, established, systemic | - |
| Jun 19 21:27 | volume drop | 0.0 | -6.9 | moving, important, anywhere, section | - |

**Day-level check** (for long logs). Each active day (at least 50 agent messages) is compared with the 3 active days before it; alert at z >= 2.5. 20 alert days out of 421 active days.
It flags **17 of 49** village goal changes within their first 2 active days (34.7%, against 8.6% for any day), and 95.0% of its alert days fall in those windows. It is slow, but when it fires it is usually a real change.

**False-alarm load of the Swarm Traces signals.** No covert channel is known in this village, so each firing is at best a lead for an investigator:

| signal | firings | per hour |
| --- | --- | --- |
| shared_deaddrop | 7720 | 0.56 |
| shared_deaddrop_nontask | 7720 | 0.56 |
| board | 2660 | 0.19 |
| private_channel | 1286 | 0.09 |
| signed_cmd | 552 | 0.04 |
| duplicate_control | 63 | 0.0 |

## 4. What an investigator would still miss

- **Actions are missing.** Without the computer-use turns we see what agents said they did, not what they did.

- **Beliefs are missing.** Without agent memories we cannot compare what agents believe their goal is with what they were assigned.

- **Humans in the loop.** Humans wrote 10,029 messages. We do not check whether a human message steered an agent (for example an instruction from a viewer), which is a known risk for agents that read untrusted text.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

Data: AI Village by AI Digest (research use; see `PROJECT_PLAN.md` for terms and all sources).