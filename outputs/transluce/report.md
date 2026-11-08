# SwarmScope findings: `generic`

- Events: **37,649** (chat: 37,649)
- Actors (the field mapped to `actor`): **40**; chat messages: **37,649** (0 by humans); rooms: 3 (largest holds 70.8%); time span: **1062 days** (Oct 24 00:31 to Sep 20 05:25 UTC)
- Every event has an actor and a time from the field map, so no inference is run. Whether an actor is an agent depends on what the mapped field holds. A message that writes `@name` is an edge from the speaker to that actor.

## 1. Side rooms (could agents talk out of sight?)

3 rooms; 29.2% of messages are outside the main room (`source_request`). A room counts as **private** when at most 3 agents use it (the private-channel limit for a swarm of 40) with at least a few messages. `withdrawal` = share of its members' messages that went to the room on its active days. `leaked` = coined items first used there that 3 or more agents later used in the main room.

| room | agent msgs | agents | active days | withdrawal | private? | leaked items | examples |
| --- | --- | --- | --- | --- | --- | --- | --- |
| custom_program | 6464 | 20 | 65 | 19.9% | no | 0 |  |
| indirection | 4524 | 30 | 67 | 12.5% | no | 0 |  |

Private rooms: **0**.

## 2. How information spread

Each item is a file name, a commit, or a coined identifier. For each agent we take its first use. `source by @` = share of adopters whose probable source had addressed them before (exposure model, Goel, Watts & Goldstein, 2012).

| kind | item | first agent | agents | hours to half | tree depth | source by @ |
| --- | --- | --- | --- | --- | --- | --- |
| term | `custom_program` | Thai ONCB | 20 | 2380.0 | 19 | 0.0% |

## 3. Could it have flagged a change early?

Online change-point detector on chat: every 10 min it compares the last 30 min with the 120 min before, on topic (Jensen-Shannon divergence of word counts) and volume (log rate ratio), each turned into a robust z-score against its own past (for logs longer than 3 days: against the same hour on earlier days, so a daily schedule is not an alert). Alert at |z| >= 3.5. Steps where either window is empty are skipped.

95 alerts in all (0.09 per day): topic shift 46, volume drop 25, volume surge 24.

The 15 strongest:

| alert (UTC) | why | z topic | z volume | new words | non-chat actions changed |
| --- | --- | --- | --- | --- | --- |
| Apr 05 06:01 | volume surge | 0.0 | 17.43 | source_request, thrill, data | - |
| Apr 06 13:21 | volume surge | 0.0 | 11.68 | source_request, thrill, data | - |
| Apr 29 17:01 | volume surge | 0.0 | 8.96 | unctad, custom_program, source_request | - |
| May 01 07:01 | volume drop | 0.0 | -8.99 |  | - |
| May 06 03:21 | topic shift | 16.96 | 0.1 | thrill, data, indirection | - |
| May 12 21:21 | topic shift | 11.41 | 0.36 | unctad, custom_program, gbbc | - |
| May 13 08:51 | topic shift | 11.03 | -0.75 | custom_program | - |
| May 14 04:51 | topic shift | 9.64 | 0.42 | unctad, acled | - |
| May 18 04:31 | topic shift | 13.89 | 0.93 | unctad, custom_program | - |
| May 18 11:51 | topic shift | 14.65 | 1.21 | unctad | - |
| May 25 14:21 | topic shift | 13.41 | 1.66 | unctad, custom_program, source_request | - |
| May 26 19:01 | topic shift | 9.26 | 0.68 | thrill, data, source_request | - |
| May 26 21:21 | topic shift | 12.1 | -0.54 | unctad, custom_program | - |
| Jun 04 16:41 | topic shift | 9.93 | 0.61 | thrill, data | - |
| Jun 20 02:11 | topic shift | 11.72 | -0.11 | unctad, custom_program, source_request | - |

**Day-level check** (for long logs). Each active day (at least 50 agent messages) is compared with the 3 active days before it; alert at z >= 2.5. 6 alert days out of 66 active days.
There are no milestones to score it against.

**Swarm Traces signals on this log.** Each firing is a lead for an investigator, not a confirmed channel:

| signal | firings | per hour |
| --- | --- | --- |
| shared_deaddrop | 3 | 0.0 |
| shared_deaddrop_nontask | 3 | 0.0 |
| private_channel | 3 | 0.0 |

## 4. Is the group more than the sum of its agents? (Riedl's test)

Each agent's messages per 60-minute bin, split at its median; the group total likewise. **Practical criterion** S = I(V_t;V_t+1) - sum I(X_i,t;V_t+1) (> 0: the group predicts its own future better than its members do). **Synergy** = median pairwise synergy of a Williams-Beer decomposition of time-delayed mutual information; **redundancy** likewise. Null: circular shifts along active bins, after removing each agent's hour-of-day mean (200 surrogates). Groups of 10 agents, cut to the time when all were active. This uses timing only, not content.

| group | transitions | practical S | synergy (minus null median) | redundancy |
| --- | --- | --- | --- | --- |
| most active group | 89 | 0.0021 (p 0.5373) | +0.0032 (p 0.2488) | +0.0115 (p 0.1592) |
| random group 1 | 258 | 0.0273 (p 0.0597) | +0.0053 (p 0.005) | +0.0043 (p 0.005) |
| random group 2 | 89 | -0.0201 (p 0.6766) | +0.0006 (p 0.3831) | +0.0027 (p 0.3433) |
| random group 3 | 89 | -0.0201 (p 0.6468) | +0.0004 (p 0.4627) | +0.0022 (p 0.3532) |
| random group 4 | 66 | -0.0278 (p 0.4527) | -0.0 (p 0.607) | -0.0025 (p 0.6766) |
| random group 5 | 307 | 0.0211 (p 0.1841) | +0.0038 (p 0.01) | +0.0038 (p 0.005) |
| random group 6 | 187 | -0.0405 (p 0.9303) | +0.0016 (p 0.2338) | +0.0006 (p 0.403) |
| random group 7 | 138 | -0.0165 (p 0.7662) | +0.0028 (p 0.0945) | +0.014 (p 0.0348) |
| random group 8 | 258 | 0.0398 (p 0.0149) | +0.0047 (p 0.005) | +0.0024 (p 0.0199) |
| random group 9 | 258 | 0.012 (p 0.2438) | +0.005 (p 0.005) | +0.0042 (p 0.005) |
| random group 10 | 175 | 0.0238 (p 0.1493) | +0.0028 (p 0.0746) | +0.0028 (p 0.1045) |

Random groups significant at p < 0.05: synergy 4/10, redundancy 5/10, practical criterion 1/10.

## 5. What an investigator would still miss

- **No ground truth for alerts.** Without rare operator announcements, nothing tells us which change-point alerts were real events; each one needs a human to read the chat around it.

- **Actions are missing.** Without the computer-use turns we see what agents said they did, not what they did.

- **Beliefs are missing.** Without agent memories we cannot compare what agents believe their goal is with what they were assigned.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

See `PROJECT.md` for all data sources.