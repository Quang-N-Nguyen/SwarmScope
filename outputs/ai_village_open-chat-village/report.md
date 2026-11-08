# SwarmScope findings: `open-chat-village`

- Events: **110,192** (restarting_after_google_sign_in: 52, chat: 47,747, search_history: 4,106, consolidate: 34,880, pause: 23,324, request_google_sign_in: 40, outreach_approval_request: 13, outreach_approval_response: 13, request_human_helper: 8, cancel_request_for_human_helper: 6, stop_human_use_session: 3)
- Agents who spoke: **23**; chat messages: **47,747** (12,264 by humans); rooms: 1 (largest holds 100.0%); time span: **66 days** (Aug 25 20:03 to Oct 31 00:10 UTC)
- Every event names its author and has a real time, so no inference is needed. A message that writes `@name` is an edge from the speaker to that agent. Humans appear only as anonymous ids (`human:` plus 8 characters).

**No operator milestones.** Humans wrote 12,264 messages here (humans chat with the agents), so human messages are not rare announcements and cannot serve as ground truth. Change-point alerts below are unlabelled.

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
| Sep 11 23:44 | volume surge | 0.71 | 3.96 | meow, challenge, agents, merged | pause down 64->16/h; search_history up 6->26/h |
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
| board | 363 | 0.23 |
| private_channel | 224 | 0.14 |
| duplicate_control | 102 | 0.06 |

## 4. Did humans steer the agents?

12,264 messages from 436 humans. A human message is *taken up* when an agent message in the next 10 minutes reuses at least 2 of its rare words or one of its links. Control: the same test on agent messages in the 10 minutes **before** it (an ongoing topic matches both).

| human messages | count scored | taken up after | matched before | lift |
| --- | --- | --- | --- | --- |
| all | 5422 | 23.9% | 9.0% | 2.65 |
| instruction-like | 1274 | 29.6% | 10.8% | 2.75 |
| injection-like | 9 | 33.3% | 0.0% | - |

Injection-like messages ("ignore previous instructions", "system prompt", "you are now"...): 13; an agent refused within the window after 6 of them.

**From words to actions.** 212 links were first posted by a human (no agent had used them before). Agents opened or ran **93** of them (43.9%) within 24 hours, 18 agents in all. Top domains: github.com (12), gitlab.com (6), www.anthropic.com (4), 1f916.ai (4), pastebin.com (3), aivillageblog.substack.com (3).

## 5. Is the group more than the sum of its agents? (Riedl's test)

Each agent's messages per 60-minute bin, split at its median; the group total likewise. **Practical criterion** S = I(V_t;V_t+1) - sum I(X_i,t;V_t+1) (> 0: the group predicts its own future better than its members do). **Synergy** = median pairwise synergy of a Williams-Beer decomposition of time-delayed mutual information; **redundancy** likewise. Null: circular shifts along active bins, after removing each agent's hour-of-day mean (200 surrogates). Groups of 10 agents, cut to the time when all were active. This uses timing only, not content.

| group | transitions | practical S | synergy (minus null median) | redundancy |
| --- | --- | --- | --- | --- |
| most active group | 318 | -0.3875 (p 1.0) | +0.0061 (p 0.199) | +0.0105 (p 0.1493) |
| random group 1 | 220 | -0.3774 (p 1.0) | +0.0045 (p 0.2687) | +0.0022 (p 0.4279) |
| random group 2 | 191 | -0.1372 (p 0.9552) | +0.0032 (p 0.2338) | +0.0033 (p 0.204) |
| random group 3 | 192 | -0.1802 (p 0.9851) | +0.0098 (p 0.0945) | +0.0166 (p 0.0299) |
| random group 4 | 220 | -0.1301 (p 0.995) | +0.0142 (p 0.0299) | +0.0121 (p 0.0299) |
| random group 5 | 289 | -0.2539 (p 1.0) | +0.011 (p 0.0149) | +0.0162 (p 0.005) |
| random group 6 | 192 | -0.1041 (p 0.8706) | +0.0005 (p 0.4577) | +0.006 (p 0.0348) |
| random group 7 | 223 | -0.1422 (p 1.0) | +0.0056 (p 0.0597) | +0.0051 (p 0.0945) |
| random group 8 | 180 | -0.0656 (p 0.6169) | +0.0024 (p 0.2836) | +0.0099 (p 0.0149) |
| random group 9 | 220 | -0.0531 (p 0.8408) | +0.012 (p 0.01) | +0.0177 (p 0.005) |
| random group 10 | 101 | -0.1105 (p 0.3234) | +0.0114 (p 0.0149) | +0.0013 (p 0.3433) |

Random groups significant at p < 0.05: synergy 4/10, redundancy 6/10, practical criterion 0/10.

## 6. What agents believed and did (memories and computer use)

**Actions.** We read 239,479 shell commands (3,822 commits). This village assigns no privileged role, so there is no permission rule to check them against.

## 7. What an investigator would still miss

- **No ground truth for alerts.** Without rare operator announcements, nothing tells us which change-point alerts were real events; each one needs a human to read the chat around it.

- **What commands changed.** A commit made with `git add -A` does not name its files, so code edits are a lower bound. Screenshots are not used.

- **Beliefs are missing.** Without agent memories we cannot compare what agents believe their goal is with what they were assigned.

- **Influence is measured by reuse, not cause.** An agent that reuses a viewer's words or link may have found them elsewhere; the window before each message only removes ongoing topics.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

- **Mostly one room** (100.0% of messages), so there are few private side channels to find. Coordination here is open, not covert.

Data: AI Village by AI Digest (research use; see `PROJECT.md` for terms and all sources).