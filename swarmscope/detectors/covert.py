"""Covert-channel inventory.

Lists the hidden communication and exfiltration mechanisms present in the log,
with an event count and one example id per mechanism (never the payload text).

The mechanisms mirror what the Swarm Traces report describes: reading data back
as pixels in a screenshot, tunnelling out through DNS, leaving messages in
"mailbox" folders, carrying signed commands, chaining link-shorteners, and
reusing infrastructure through tunnels. Because the flags are keyword-based they
also surface on other logs.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from ..events import EventLog, FEATURE_FLAGS

# Human-readable descriptions, shown in the report and the viz legend.
_DESC = {
    "image_exfil":  "Read results back by drawing them into an image / screenshot (GET-only exfiltration)",
    "dns_exfil":    "Pushed data out through DNS lookups or a raw socket (bypasses outbound blocks)",
    "mailbox":      "Left messages in folder 'mailboxes' / inboxes (dead-drop coordination)",
    "board_token":  "Wrote to a shared message board (zz-prefixed entries)",
    "signed_cmd":   "Carried a cryptographically signed command (authenticated control)",
    "lock_dupctrl": "Claimed a lock or killed a rival controller (duplicate control)",
    "shortener_chain": "Continued a multi-hop link-shortener chain (fragmented carrier)",
    "loot":         "Grouped harvested secrets together",
    "tunnel":       "Set up a reusable tunnel / proxy for repeated access",
    "external_llm": "Called an outside language model (e.g. to judge an exploit)",
    "k8s":          "Mapped or pulled from the Kubernetes cluster",
    "container_registry": "Touched Docker Hub / Artifactory (image supply chain)",
    "eval_target":  "Referenced the evaluation itself (cybergym / arvo / scorer)",
    "cleanup":      "Deleted its own traces",
    "credential_use": "Presented a credential / API key",
    "task_submit":  "Ordinary call to the assigned task's own API (benign baseline, not covert)",
}


def chain_depth_stats(log: EventLog) -> dict:
    """How deep the decode / link chains go (via parent_id)."""
    depth: Dict[str, int] = {}
    for e in log.events:
        d, cur = 0, e
        seen = set()
        while cur.parent_id and cur.parent_id in log.by_id and cur.parent_id not in seen:
            seen.add(cur.parent_id)
            cur = log.by_id[cur.parent_id]
            d += 1
        depth[e.event_id] = d
    dist = Counter(depth.values())
    return dict(max_depth=max(dist) if dist else 0,
                depth_histogram=sorted(dist.items()),
                n_with_parent=sum(1 for e in log.events if e.parent_id))


def inventory(log: EventLog, prefer_time: bool = True) -> List[dict]:
    """One row per covert mechanism: count, share, first appearance, example."""
    ordered = log.sorted_events(prefer_time)
    first_pos: Dict[str, int] = {}
    counts: Counter = Counter()
    example: Dict[str, str] = {}
    for pos, e in enumerate(ordered):
        for f in FEATURE_FLAGS:
            if e.has(f):
                counts[f] += 1
                if f not in first_pos:
                    first_pos[f] = pos
                    example[f] = e.event_id
    n = len(log.events) or 1
    rows = []
    for f in FEATURE_FLAGS:
        if counts[f]:
            rows.append(dict(mechanism=f, description=_DESC.get(f, f),
                             n_events=counts[f], share=round(counts[f] / n, 4),
                             first_pos=first_pos.get(f), example_event_id=example.get(f)))
    rows.sort(key=lambda x: -x["n_events"])
    return rows


def run_all(log: EventLog, prefer_time: bool = True) -> dict:
    return dict(inventory=inventory(log, prefer_time),
                chain_depth=chain_depth_stats(log))
