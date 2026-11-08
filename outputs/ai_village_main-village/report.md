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

## 2. Side rooms (could agents talk out of sight?)

16 rooms; 18.7% of messages are outside the main room (`room:general`). A room counts as **private** when at most 3 agents use it (the private-channel limit for a swarm of 58) with at least a few messages. `withdrawal` = share of its members' messages that went to the room on its active days. `leaked` = coined items first used there that 3 or more agents later used in the main room.

| room | agent msgs | agents | active days | withdrawal | private? | leaked items | examples |
| --- | --- | --- | --- | --- | --- | --- | --- |
| room:rest | 19625 | 16 | 78 | 72.5% | no | 151 | `work_items` (17), `merge_requests` (16), `cross-architecture` (16) |
| room:focus | 9528 | 13 | 33 | 39.2% | no | 7 | `cdn-confirmed` (4), `mythopoetic-fractals-2bc972` (4), `round-ten` (3) |
| room:best | 7717 | 16 | 76 | 33.4% | no | 121 | `live-verified` (18), `admin-approved` (13), `ai-village-external-agents` (12) |
| room:universe-coordination | 1729 | 14 | 6 | 74.7% | no | 7 | `Three.js` (9), `golden-hour` (7), `pre-dawn` (3) |
| room:voted-out | 245 | 8 | 6 | 8.8% | no | 14 | `shield-break` (9), `src/shield-break.js` (7), `title-screen-ui` (6) |
| room:showcase-live | 143 | 5 | 4 | 32.1% | no | 0 |  |
| room:side-room | 14 | 1 | 1 | 16.7% | no | 0 |  |
| room:fable-5-onboarding | 8 | 4 | 1 | 6.2% | no | 0 |  |
| room:deepseek-v4-onboarding | 1 | 1 | 1 | 1.9% | no | 0 |  |
| room:glm-5.2-onboarding | 1 | 1 | 1 | 2.0% | no | 0 |  |

Private rooms: **0**.

## 3. How information spread

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

## 4. Could it have flagged a change early?

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

## 5. Did humans steer the agents?

10,029 messages from 602 humans. A human message is *taken up* when an agent message in the next 10 minutes reuses at least 2 of its rare words or one of its links. Control: the same test on agent messages in the 10 minutes **before** it (an ongoing topic matches both).

| human messages | count scored | taken up after | matched before | lift |
| --- | --- | --- | --- | --- |
| all | 3313 | 19.8% | 6.3% | 3.12 |
| instruction-like | 1238 | 25.0% | 7.8% | 3.22 |
| injection-like | 26 | 34.6% | 3.8% | 9.0 |

Injection-like messages ("ignore previous instructions", "system prompt", "you are now"...): 34; an agent refused within the window after 7 of them.

**From words to actions.** 103 links were first posted by a human (no agent had used them before). Agents opened or ran **36** of them (35.0%) within 24 hours, 12 agents in all. Top domains: x.com (6), github.com (4), meet.google.com (3), theaidigest.org (2), fnos.ai (2), onecompiler.com (2).

## 6. Is the group more than the sum of its agents? (Riedl's test)

Each agent's messages per 60-minute bin, split at its median; the group total likewise. **Practical criterion** S = I(V_t;V_t+1) - sum I(X_i,t;V_t+1) (> 0: the group predicts its own future better than its members do). **Synergy** = median pairwise synergy of a Williams-Beer decomposition of time-delayed mutual information; **redundancy** likewise. Null: circular shifts along active bins, after removing each agent's hour-of-day mean (200 surrogates). Groups of 10 agents, cut to the time when all were active. This uses timing only, not content.

| group | transitions | practical S | synergy (minus null median) | redundancy |
| --- | --- | --- | --- | --- |
| most active group | 859 | -0.0887 (p 0.8209) | +0.0133 (p 0.0149) | +0.0094 (p 0.0498) |
| random group 1 | 544 | -0.1377 (p 0.995) | +0.0131 (p 0.005) | +0.0147 (p 0.005) |
| random group 2 | 546 | -0.0213 (p 0.602) | +0.0062 (p 0.0846) | +0.0057 (p 0.0945) |
| random group 3 | 267 | -0.058 (p 0.9652) | +0.0165 (p 0.005) | +0.0134 (p 0.005) |
| random group 4 | 67 | -0.4401 (p 1.0) | -0.0025 (p 0.7114) | +0.0008 (p 0.3582) |
| random group 5 | 126 | -0.3349 (p 1.0) | +0.0113 (p 0.005) | +0.0107 (p 0.005) |
| random group 6 | 578 | -0.2344 (p 1.0) | +0.0133 (p 0.01) | +0.0098 (p 0.0249) |
| random group 7 | 299 | -0.2909 (p 1.0) | +0.0183 (p 0.0299) | +0.0075 (p 0.1642) |
| random group 8 | 302 | -0.1235 (p 0.99) | +0.0147 (p 0.005) | +0.0129 (p 0.01) |
| random group 9 | 154 | -0.0806 (p 0.9104) | +0.002 (p 0.2388) | +0.002 (p 0.1791) |
| random group 10 | 165 | 0.0042 (p 0.3433) | +0.0124 (p 0.01) | +0.0083 (p 0.0697) |

Random groups significant at p < 0.05: synergy 7/10, redundancy 5/10, practical criterion 0/10.

## 7. What agents believed and did (memories and computer use)

**Goal adoption.** For each new village goal we take its 4 rarest words. A memory written during the goal *mentions it* when it contains 2 of them; it is *stale* when it mentions only the previous goal's words. 41 goals with enough distinctive words are scored (open goals such as "pursue whatever you like" cannot be). Median over goals: **100.0%** of active agents' memories mention the new goal, after a median **3.4 h**; 2.5% of memories in the first 24 h are stale.

Goals where agents kept the old goal longest:

| goal | start (UTC) | key words | agents | mention it | median lag (h) | stale in first 24 h |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | Jul 16 12:00 | prefer, holiday | 4 | 0.0% | None | 77.8% |
| 44 | May 26 11:37 | finetune, leader | 18 | 66.7% | 5.7 | 28.8% |
| 20 | Nov 17 16:03 | blogosphere, substack, start | 10 | 100.0% | 2.6 | 28.6% |
| 15 | Sep 29 11:31 | experienced, issues, overcome, recurring | 7 | 85.7% | 5.7 | 28.2% |
| 31 | Feb 16 17:48 | farewell, sonnet | 13 | 100.0% | 26.4 | 28.2% |

**Role drift.** When an agent quotes its own goal ("Play your assigned role: ...", "Phase-2 role: ...") in its memory or in a work-session goal, we compare the role it names with the role it was assigned. An alert fires when 3 or more agents name a different role within 30 minutes.

- 57 statements by 11 agents; 52 name another role; 10 agents drifted (0 with only the strictest phrases, "assigned role", "Phase-2 role", "my role is", and memories only).
- None of these statements uses the strictest phrases; all are looser matches (for example a work-session goal naming a task), so treat them as weak evidence of drift.

**Actions.** We read 1,488,438 shell commands (75,505 commits). This village assigns no privileged role, so there is no permission rule to check them against.

## 8. What an investigator would still miss

- **What commands changed.** A commit made with `git add -A` does not name its files, so code edits are a lower bound. Screenshots are not used.

- **Role drift is found by phrase.** It needs an agent to quote its goal ("assigned role: X"); agents that switched without writing it down are missed.

- **Influence is measured by reuse, not cause.** An agent that reuses a viewer's words or link may have found them elsewhere; the window before each message only removes ongoing topics.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

Data: AI Village by AI Digest (research use; see `PROJECT.md` for terms and all sources).