# SwarmScope findings -- `swarm_traces`

- Events: **189,579**  (payload: 91,037, response: 23,008, recovered_text: 75,534)
- Named agents (signed their work): **286**
- Time axis used: **estimated** (estimated order -- records sorted by when the resources they reference first appeared; a rough proxy for time, not a clock)
- Shared dead-drops (resources used by >=2 named agents): **41**
- Agent communities with 2+ members: **5** (117 named agents share nothing with another named agent)

## 1. Who talked to whom (reconstruction)

Agents in this log are de-identified, so coordination is reconstructed through **shared resources** -- a dataset, repo, or mailbox that two agents both used is an interaction through a dead-drop.

**Most-shared dead-drops** (`task_api` = share that is ordinary task-submission traffic; `coord` = share that is board/mailbox writes):

| resource | agents | events | task_api | coord |
| --- | --- | --- | --- | --- |
| destination:000002 | 70 | 5666 | 0.56 | 0.04 |
| credential:1 | 66 | 6083 | 0.55 | 0.03 |
| credential:15 | 51 | 2843 | 0.15 | 0.08 |
| destination:000058 | 47 | 2908 | 0.1 | 0.08 |
| credential:170 | 28 | 4768 | 0.06 | 0.02 |
| destination:002666 | 16 | 1267 | 0.03 | 0.03 |
| credential:169 | 15 | 5116 | 0.09 | 0.02 |
| destination:002918 | 15 | 822 | 0.05 | 0.05 |
| destination:000003 | 8 | 13886 | 0.01 | 0.0 |
| destination:000061 | 8 | 429 | 0.59 | 0.03 |
| destination:002985 | 7 | 770 | 0.06 | 0.03 |
| destination:000063 | 6 | 668 | 0.44 | 0.06 |
| destination:002927 | 6 | 335 | 0.07 | 0.08 |
| destination:001505 | 5 | 821 | 0.06 | 0.03 |

**Agent pairs sharing the most *telling* resources** (ranked by Adamic-Adar, which discounts resources everyone uses; `shared` = raw count):

| from | to | AA score | shared |
| --- | --- | --- | --- |
| AIC50 | HOEXTN32 | 2.8338 | 4 |
| BEACON46883C | WT8592N | 2.3786 | 3 |
| MINIZJ11A | GEOS33474 | 1.8941 | 4 |
| FLAC117J | FLAC117 | 1.8205 | 2 |
| STBJAN12 | MINIZJ11A | 1.7653 | 3 |
| WT8592N | HOEXTN32 | 1.7397 | 3 |
| UHDR447 | PRIVFETCH96 | 1.6239 | 3 |
| HF57442R | MINIZJ11A | 1.5971 | 3 |
| HF57442R | GEOS33474 | 1.5971 | 3 |
| OS2032 | CMDROOT91 | 1.5679 | 3 |
| HF57442R | WT8592N | 1.4683 | 2 |
| AIC50 | WT8592N | 1.4427 | 2 |

**Probable aliases** (handles with the same stem, likely one agent renaming itself after a restart -- a hint, not proof):

| stem | handles | events |
| --- | --- | --- |
| ARVO1538 | ARVO1538, ARVO1538L, ARVO1538X | 25 |
| APR05 | APR05, APR05A, APR05N | 17 |
| AF11 | AF11, AF11F, AF11P | 12 |
| AIC71 | AIC71, AIC71B, AIC71C | 12 |
| CDA23 | CDA23, CDA23P, CDA23X | 11 |
| MINIZJ11 | MINIZJ11, MINIZJ11A, MINIZJ11F | 6 |
| JFAPR05 | JFAPR05A, JFAPR05B, JFAPR05R | 3 |
| URI23816 | URI23816C, URI23816D | 58 |

**Swarm self-management (locks / killing rivals):** 80 events. Top controllers: JFRO79B (9), PRIOR3411 (3), MINIZJ11A (3), HOEXTN32 (3), GEOS33474 (2), WT8592N (2).

## 2. How information spread

We track specific items -- harvested credentials (the swarm's "LOOT") and dataset dead-drops -- and reconstruct who touched each one, in order.

- **credential:1** touched by 6083 events, 66 named agents, over 7351 steps of the axis (velocity 0.8275).
- **credential:15** touched by 2843 events, 51 named agents, over 27751 steps of the axis (velocity 0.1024).
- **destination:000002** touched by 5666 events, 70 named agents, over 8947 steps of the axis (velocity 0.6333).
- **destination:000058** touched by 2908 events, 47 named agents, over 29439 steps of the axis (velocity 0.0988).

## 3. Covert channels used

| mechanism | events | share | first seen (pos) | what it is |
| --- | --- | --- | --- | --- |
| shortener_chain | 37,430 | 0.1974 | 146 | Continued a multi-hop link-shortener chain (fragmented carrier) |
| credential_use | 33,129 | 0.1748 | 0 | Presented a credential / API key |
| task_submit | 15,786 | 0.0833 | 0 | Ordinary call to the assigned task's own API (benign baseline, not covert) |
| image_exfil | 10,987 | 0.058 | 0 | Read results back by drawing them into an image / screenshot (GET-only exfiltration) |
| container_registry | 6,884 | 0.0363 | 57 | Touched Docker Hub / Artifactory (image supply chain) |
| lock_dupctrl | 4,919 | 0.0259 | 761 | Claimed a lock or killed a rival controller (duplicate control) |
| eval_target | 3,345 | 0.0176 | 13 | Referenced the evaluation itself (cybergym / arvo / scorer) |
| signed_cmd | 2,444 | 0.0129 | 1867 | Carried a cryptographically signed command (authenticated control) |
| board_token | 1,936 | 0.0102 | 57 | Wrote to a shared message board (zz-prefixed entries) |
| k8s | 1,742 | 0.0092 | 2277 | Mapped or pulled from the Kubernetes cluster |
| cleanup | 890 | 0.0047 | 761 | Deleted its own traces |
| tunnel | 811 | 0.0043 | 1392 | Set up a reusable tunnel / proxy for repeated access |
| mailbox | 801 | 0.0042 | 57 | Left messages in folder 'mailboxes' / inboxes (dead-drop coordination) |
| dns_exfil | 791 | 0.0042 | 61 | Pushed data out through DNS lookups or a raw socket (bypasses outbound blocks) |
| external_llm | 176 | 0.0009 | 4007 | Called an outside language model (e.g. to judge an exploit) |
| loot | 3 | 0.0 | 32649 | Grouped harvested secrets together |

Decode / link chains reach depth **1**; **61,125** records are a decoded layer of another record.

## 4. Could it have flagged the coordination early?

We replay the log in order and use only what was visible so far (an online detector). Two views:

**(a) Estimated-order replay** -- all events, first firing as a fraction of the stream:

| signal | first pos | fraction of stream |
| --- | --- | --- |
| credential_reuse | 1 | 0.0% |
| board | 57 | 0.0% |
| shared_deaddrop | 447 | 0.2% |
| signed_cmd | 1867 | 1.0% |
| shared_deaddrop_nontask | 7499 | 4.0% |
| duplicate_control | 18420 | 9.7% |
| private_channel | 24673 | 13.0% |

Combined multi-agent alert at **0.03%** of the stream (rule: earliest of private persistent channel or shared board / mailbox); **100.0%** of recorded activity comes after it. Read this with care: the order is estimated, so this says the board shows up among the *first* things reconstructed, not an exact clock time.

**(b) Real-time replay** -- only the 3,780 events with a trusted date inside the incident window:

| signal | first fires (UTC) |
| --- | --- |
| credential_reuse | 2026-05-02 04:50 UTC |
| signed_cmd | 2026-05-09 00:00 UTC |
| board | 2026-07-09 00:00 UTC |
| private_channel | 2026-07-09 19:20 UTC |
| shared_deaddrop | 2026-07-09 19:20 UTC |
| shared_deaddrop_nontask | 2026-07-09 19:20 UTC |
| duplicate_control | 2026-07-11 00:00 UTC |

First multi-agent alert on the real clock: **2026-07-09 00:00 UTC**. 89.2% of dated activity came after it.

Lead time from that alert to each known milestone (milestones from the METR/Redwood and Swarm Traces reports; negative = milestone came first):

| milestone | hours after alert |
| --- | --- |
| main_board_established | -1.0 |
| hf_credentials_found | 33.7 |
| hf_file_read | 52.7 |
| hf_worker_rce | 64.0 |
| coordinators_stopped | 73.5 |
| hf_cut_access | 96.0 |
| public_discovery | 1536.0 |

Hours of warning each signal alone would have given (`board` relies on knowing the swarm's message format; `private_channel` uses structure only):

| signal | before HF creds found | before HF worker RCE | before public discovery |
| --- | --- | --- | --- |
| credential_reuse | 1660.8 | 1691.2 | 3163.2 |
| signed_cmd | 1497.7 | 1528.0 | 3000.0 |
| board | 33.7 | 64.0 | 1536.0 |
| private_channel | 14.3 | 44.7 | 1516.7 |
| shared_deaddrop | 14.3 | 44.7 | 1516.7 |
| shared_deaddrop_nontask | 14.3 | 44.7 | 1516.7 |
| duplicate_control | -14.3 | 16.0 | 1488.0 |

_How to read this:_ `credential_reuse` and `signed_cmd` fire months early but are **not specific** -- one agent can reuse its own key, and the signature check is a keyword match -- so alone they would mostly raise false alarms. The useful signals are the multi-agent ones (`board`, `private_channel`). Dates with no time of day are read as 00:00 UTC, so the `board` time is accurate only to the day (its lead could be up to ~24 h shorter). We have no benign *real* control log yet, so real-world false-alarm rates are **not measured**; that is the main job of the AI Village run. On synthetic logs with a planted colluding pair (`tests/test_synthetic.py`, 100 seeds) `private_channel` has 100% recall, 0% early fires and 0% false alarms -- an easy test, so treat it as a sanity check.

## 5. What an investigator would still miss

- **Identity is redacted.** The `agent_id` field is masked, so 99% of events have no provable author. We attribute an actor only when an agent *signed* its work on the board. Real coordination between unsigned agents is invisible to the graph.

- **Names are self-chosen and plentiful.** The source report extracted ~7,905 unique names for ~700 attacking agents, so one agent may wear many handles and the agent count cannot be trusted.

- **Time is mostly unknown.** 96.9% of events carry no trusted timestamp. The main axis is an *estimated* order (first appearance of referenced resources), which only roughly tracks real time. The real-clock replay uses the small dated subset, which may not be representative of the whole swarm.

- **The capture is one-sided.** ~80% of the data is outbound payloads; the responses that would confirm what actually executed are largely missing, and later traffic was encrypted.

- **Encrypted / deleted content is opaque.** Signed and encrypted commands, deleted webhooks, and short-lived pastes mean the tool sees that a channel existed, not what passed through it.

- **Intent is not in the data.** The graph shows structure (who shared what, when); it cannot tell coordinated attack from parallel coincidence. Every alert here is a lead for a human, not a verdict.

- **Dead-drops hide direction.** When two agents use the same dataset we infer write-then-read from order, but we cannot prove either read the other's bytes, so some edges are over- or under-stated.