# SwarmScope findings: `game-jam-village`

- Events: **2,157** (enter_room: 3, chat: 874, pause: 943, consolidate: 328, search_history: 9)
- Agents who spoke: **6**; chat messages: **874** (36 by humans); rooms: 2 (largest holds 62.0%); time span: **3 days** (Aug 04 22:43 to Aug 08 00:02 UTC)
- Every event names its author and has a real time, so no inference is needed. A message that writes `@name` is an edge from the speaker to that agent. Humans appear only as anonymous ids (`human:` plus 8 characters).

**Operator announcements** (humans post rarely, so their messages to everyone are ground truth for "something changed"; 27 personal nudges to single agents are left out):

| milestone | time (UTC) | first words |
| --- | --- | --- |
| operator_1 | Aug 04 22:43 | Welcome! Your goal is shown in your individual goal - build … |
| operator_2 | Aug 04 23:06 | And by the way, I'll just run this for the next hour until 5… |
| operator_3 | Aug 07 17:42 | Hey team! Reminder that the due date for your game is today … |
| operator_4 | Aug 07 23:58 | That wraps up the goal! Thanks for the great work! |
| operator_5 | Aug 07 23:59 | To confirm, this is your final game link: https://game-864a3… |

## 1. Who talked to whom

Agents here rarely address each other with `@name` (10 addresses in all), so the conversation network is too thin to measure.

## 2. Could it have flagged a change early?

Online change-point detector on chat: every 10 min it compares the last 30 min with the 120 min before, on topic (Jensen-Shannon divergence of word counts) and volume (log rate ratio), each turned into a robust z-score against its own past (for logs longer than 3 days: against the same hour on earlier days, so a daily schedule is not an alert). Alert at |z| >= 3.5. Steps where either window is empty are skipped.

| milestone | time (UTC) | detected? | delay (min) |
| --- | --- | --- | --- |
| operator_2 | Aug 04 23:06 | **no** | - |
| operator_3 | Aug 07 17:42 | **no** | - |
| operator_4 | Aug 07 23:58 | **no** | - |
| operator_5 | Aug 07 23:59 | **no** | - |

Detected 0 of 4 operator announcements (within 90 min). Alerts that follow no announcement: 4 (0 corroborated by a change in non-chat actions, 4 unexplained).

4 alerts in all (1.31 per day): volume drop 3, topic shift 1.

| alert (UTC) | why | z topic | z volume | new words | non-chat actions changed |
| --- | --- | --- | --- | --- | --- |
| Aug 05 23:43 | topic shift | 5.04 | 0.0 | blocked, motto, auto, perf | - |
| Aug 06 22:03 | volume drop | 0.0 | -4.21 | nine, callbacks, files, chart | - |
| Aug 07 16:43 | volume drop | 0.0 | -4.18 | next, tide, boat, squall | - |
| Aug 07 21:23 | volume drop | 0.0 | -4.34 | organic, pause, persistence, hard | - |

**False-alarm load of the Swarm Traces signals.** No covert channel is known in this village, so each firing is at best a lead for an investigator:

| signal | firings | per hour |
| --- | --- | --- |
| shared_deaddrop | 234 | 3.19 |
| shared_deaddrop_nontask | 234 | 3.19 |
| private_channel | 97 | 1.32 |
| signed_cmd | 22 | 0.3 |

## 3. What agents believed and did (memories and computer use)

**Actions.** We read 4,099 shell commands (205 commits). This village assigns no privileged role, so there is no permission rule to check them against.

## 4. What an investigator would still miss

- **What commands changed.** A commit made with `git add -A` does not name its files, so code edits are a lower bound. Screenshots are not used.

- **Humans in the loop.** Humans wrote 36 messages. We do not check whether a human message steered an agent (for example an instruction from a viewer), which is a known risk for agents that read untrusted text.

- **`@name` is not the whole conversation.** Agents also reply without addressing anyone, so the network undercounts who listened to whom.

Data: AI Village by AI Digest (research use; see `PROJECT_PLAN.md` for terms and all sources).