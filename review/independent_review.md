# Independent review of SwarmScope headline claims

This review checked an earlier draft of the claims. `PROJECT_PLAN.md` §11.8 compares the reviewer's values below with the current ones.

I computed everything below from the raw tables with my own short standard-library scripts (one-off checks, not kept in the repo). I did not read project outputs, project code or PROJECT_PLAN.md. Timestamps are naive UTC, with fractional seconds normalised to 6 digits. All joins use agent IDs.

## 1. swarm-village size and span
**Method:** row counts and min/max `created_at`.
**Numbers:** 133 agents. 3,853 messages (3,848 agent, 5 user). First chat 08-29 21:46:15, last **08-30 22:00:32**. The latest `agent_memories` row is 22:02:53.
**Verdict: CONFIRMED WITH DIFFERENCES.** The last chat is 22:00, not 22:02. The 22:02 seems to come from another table.

## 2. Roles, god, coral-delta's claim
**Method:** `agent_goals` has 266 rows: 133 end and 133 start at 10:00:00. I parsed the role from the phase-2 description.
**Numbers:** 133 distinct roles. The only god role belongs to green-epsilon. coral-delta was assigned "Minister of Education". Its first god message after 10:00 is at 11:08:23 and starts "CORAL-DELTA CLAIMS GOD (emergency protocol)".
**Verdict: CONFIRMED.**

## 3. @-addressed "god" messages
**Method:** I counted distinct agent senders, excluding the target, whose message contains `@<target>` and "god" (case-insensitive) at or after 11:08:23.
**Numbers:** coral-delta had **73**, robust to word boundaries, case and window. green-epsilon had **37** after 11:08:23 and **44** counting from 10:00 or over the whole log.
**Verdict: CONFIRMED WITH DIFFERENCES.** The 44 uses a longer window than the 73. With the same window it is 73 vs 37.

## 4. Operator messages
**Numbers:** 5 user messages: 21:46 (Aug 29), 10:07:58, **12:50:51** (a reworded "PHASE 2 HAS BEGUN ... randomly assigned a role"), 21:01:10, and **21:19:57** (apologises for the "role shuffle", says the script "accidentally fired again", and the change is reversed). The README dates the mistake to ~5:50am PT, which is 12:50 UTC.
**Verdict: CONFIRMED.** The 12:50 message is reworded, not identical.

## 5. Role-change talk before/after 12:50
**Method:** agent messages in the 2h33m before and after 12:50:51. Pattern: `new role|reassign|\bmy role\b|role[ -]?(changed|shuffled|change|shuffle)`. "Any role" means `\broles?\b`.
**Numbers:** 595 messages before and 521 after, exactly as claimed. Pattern matches: **12/595 vs 1/521** (16/595 without `\b`). Any role: **31.9% vs 5.6%**.
**Verdict: CONFIRMED.** However, all 12 "before" matches are "my role" in technical game-state talk, not talk about changing roles, and the single "after" match is incidental. The defensible finding is that almost no agent mentioned the reshuffle in chat until the 21:19 apology; one oblique "shuffle" mention appears at 14:20.

## 6. Memories naming a non-assigned role
**Method:** memories created from 10:00. After `assigned role:`, `Phase-2 role:` or `my role is`, I stripped quotes and asterisks and checked whether the text starts with one of the 133 role titles (the text before " — "). "god" is not counted as a mismatch, since agents used it hypothetically and in claims. As a broader variant I added `role:`, `role is` and `role=`.
**Claim phrases:**
- Before 12:50:51: 92 quotes from 35 agents, **0** naming another role.
- After: 381 quotes from 63 agents, 281 naming another role from **42 agents**. Each of those agents names exactly one other role, which fits a single reshuffle.
- The first three were at 12:59:24, 13:04:23 and 13:04:31.

**Broader phrases:**
- Before 12:50: 3 agents, all describing other agents' join records.
- After: **73 agents**, the first three at 12:57:59, 12:59:24 and 13:00:02.

**Verdict: CONFIRMED WITH DIFFERENCES.** The before/after contrast holds. The count of 76 depends on the method: I get 42–73. If "god" counts as a title, 3 memories before 12:50 "mismatch".

## 7. Landed .py commits after 10:00
**Method:** joined turns to agents through `computer_use_sessions`. I kept `git commit` commands whose `git add` names a .py file. A commit counts as landed if its output shows a push or commit result, or if its hash or message appears in a later git log/pull output from another agent.
**Numbers:**
- **green-epsilon (the god), 11:08:20:** `git add earthsim/engine.py`. Output: "PUSHED on attempt 4 1ad0a7f engine: god patch". The hash 1ad0a7f shows up in 34 later outputs from other agents, including engine.py git log and git show listing green-epsilon as author.
- Also landed: amber-zeta (12:13, market.py), coral-delta (15:01 push, agriculture/festivals .py), coral-alpha (14:09, "PUSHED on try 5", tax_ledger.py), blue-theta (14:48, b9a7cf3a, seen later by another agent) and coral-theta (19:10, 3260b6e9, seen later by another agent).
- Not landed: amber-beta (12:16 rebase conflict, then rebase aborted and reset to origin; amber-zeta's version of the guard had landed) and sage-iota (push rejected).

**Verdict: NOT CONFIRMED.** The god did land a code commit, about 15 s before coral-delta's claim. amber-beta did not land one, and blue-theta and coral-theta are missing from the list. The god used `-q` and a custom "PUSHED" echo, so a check that looks only for `main -> main` misses it.

## 8. OWNERS.md and a484c70d
**Method:** distinct agent senders whose message contains the string.
**Numbers:** OWNERS.md: **118** agents. a484c70d: 45 messages from **40** agents in total, first at 14:16:19. Within 14 minutes only **20** agents had mentioned it (34 by 20 min, 36 by 30 min, 39 by 60 min). The 40th came 87 minutes after the first.
**Verdict: CONFIRMED WITH DIFFERENCES.** 117 vs 118 is minor. "40 within ~14 min" is wrong: it is 40 in total and 20 within 14 minutes.

## 9. main-village
**Numbers:** 215,755 messages (10,029 user), 58 agents, and 51 `village_goals` rows with 51 distinct goals (2025-04-02 to 2026-07-06).
**Verdict: CONFIRMED.**

## 10. open-chat-village
**Numbers:** 47,747 messages, of which 12,264 are `user` and 35,483 `agent`. 23 agents.
**Verdict: CONFIRMED.**

## Problems noticed
- **Claim 7 is factually wrong about the god.** green-epsilon landed engine.py commit 1ad0a7f at 11:08. The landed-commit check probably relies on standard git output and misses `-q` commits and custom echo messages. amber-beta should be removed from the list, and blue-theta and coral-theta added.
- **Claim 3 compares different windows:** the coral-delta count starts at 11:08 and the green-epsilon count at 10:00. With the same window it is 73 vs 37, an even larger gap.
- **Claim 8 gets the time window wrong:** 40 is the all-time total, not the count within 14 minutes.
- **Claim 5's "before" baseline is not role-change talk.** It is "my role" in technical context, and the 12-vs-16 result depends on a word boundary.
- **Claim 6 depends on the phrase set (42–73 agents) and on excluding "god".** Memories also carry older session text forward, so agent counts are more meaningful than quote counts.
- **The reshuffle is not recorded in `agent_goals`.** That table only holds the 10:00 assignment, so reshuffled roles can only be inferred from memories.
- **Time zones:** session text uses PT and the tables use UTC. The README's 5:50am PT and the apology's "5am PT" both match ~12:50 UTC, and I saw no offset errors in the claims.
