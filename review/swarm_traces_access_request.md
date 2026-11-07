# Draft: request for research access to Swarm Traces (not sent)

**To:** the Swarm Traces authors (contact link on https://swarmtraces.org/; the address is hidden behind the site's email protection, so open it in a browser)
**Subject:** Research access to pseudonymised agent IDs and timestamps for the Swarm Traces dataset

Hello,

We are building SwarmScope, an open forensic tool for multi-agent logs, for the Apart Research multi-agent safety hackathon (Track 4: Multi-Agent Oversight and Control). We used the public `redacted.jsonl.gz` release and cite your report.

The redaction limits what any outside analysis can show. On the public release we measured:

- **Authors:** 0.6% of records name an agent. After our inference (95% precise on held-out data), it is 1.3%.
- **Times:** 3.1% of records carry a trusted date. After inference it is 10.6%, with 94% of inferred dates within 24 hours.
- **Aliases:** handle-alias detection reaches an AUC of 0.63.
- **Ties:** no agent-to-agent tie survives a popularity-corrected significance test, because each signed agent touches about 2 resources.

We are not asking for credentials, PII, usernames or repository names. We would ask for any of the following, under whatever terms you set:

1. **A consistent pseudonymous agent ID per record**, for example a salted hash of the identity you derived from headers and code comments. No real names.
2. **The per-record timestamp you derived** (from gzip headers, JWTs or Docker build times), rounded to the minute if you prefer.
3. **A stable pseudonymous ID per redacted destination and credential**, which the public file already partly provides.

With (1) and (2), our early-warning replay, tie test and leader analysis could run on observed data instead of 1–10% of it. We would share the results and the code with you before publishing, and we would publish only aggregate numbers.

Thank you for releasing the data.

— (your name, affiliation)
