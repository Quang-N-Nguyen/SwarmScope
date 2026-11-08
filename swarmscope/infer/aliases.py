"""Which handles are probably one agent? Record linkage on behaviour.

Agents choose their own names, so one agent can show up under several handles
(the Swarm Traces authors found 7,905 names for at most ~1,200 agents on the board,
~700 of whom attacked Hugging Face). We
look for handles that share **personal** identifiers: things one agent uses
for itself, such as one proxy URL, one whoami name, or one workload id. Shared
*team* resources (a common dead-drop dataset) do not count, because
collaborators share those too.

Score for a pair of handles A and B (Adamic & Adar, 2003):

    score(A, B) = sum over personal identifiers both used of 1 / log(1 + k)

where k is the number of handles that used that identifier. Example: A and B
both used proxy URL PROXY.4.72, and only they did (k = 2), so the score is
1 / log(3) = 0.91. If 10 handles used it, it adds only 1 / log(11) = 0.42.

This is the record-linkage idea of Fellegi & Sunter (1969) in its simplest
form: agreement on rare fields is strong evidence of a match.

How good is it? We have one weak ground truth: handles with the same name
stem (URI23816C and URI23816D) are often the same agent after a restart. We
report how well the score separates same-stem pairs from random pairs (AUC).
Caution: many stems look like benchmark task names (LIBJXL3733, SKIA6295), so
two agents on the same task may share a stem without being one agent.
"""

from __future__ import annotations

import itertools
import math
import random
import re
from collections import Counter, defaultdict
from typing import Dict, List, Set

from ..events import EventLog
from ..extract import PERSONAL_FAMILIES

_STEM = re.compile(r"^([A-Z]+\d+)")


def stem(h: str) -> str:
    m = _STEM.match(h)
    return m.group(1) if m else h


def profiles(log: EventLog, families=PERSONAL_FAMILIES) -> Dict[str, Set[tuple]]:
    """Personal identifiers seen with each observed handle."""
    prof: Dict[str, Set[tuple]] = defaultdict(set)
    for e in log.events:
        if not e.actor:
            continue
        for fam in families:
            for v in e.fingerprints.get(fam, ()):
                prof[e.actor].add((fam, v))
    return prof


def score_pairs(prof: Dict[str, Set[tuple]]) -> Dict[tuple, float]:
    usage: Counter = Counter()
    holders: Dict[tuple, List[str]] = defaultdict(list)
    for h, vals in prof.items():
        for v in vals:
            usage[v] += 1
            holders[v].append(h)
    scores: Dict[tuple, float] = defaultdict(float)
    for v, hs in holders.items():
        if len(hs) < 2:
            continue
        w = 1.0 / math.log(1 + len(hs))
        for a, b in itertools.combinations(sorted(hs), 2):
            scores[(a, b)] += w
    return scores


def _auc(pos: List[float], neg: List[float]) -> float:
    if not pos or not neg:
        return float("nan")
    gt = sum(1 for x in pos for y in neg if x > y)
    eq = sum(1 for x in pos for y in neg if x == y)
    return (gt + 0.5 * eq) / (len(pos) * len(neg))


def run(log: EventLog, top: int = 30, neg_sample: int = 5000, seed: int = 0) -> dict:
    prof = profiles(log)
    handles = sorted({e.actor for e in log.events if e.actor})
    scores = score_pairs(prof)
    pairs = list(itertools.combinations(handles, 2))
    pos = [p for p in pairs if stem(p[0]) == stem(p[1])]
    neg_all = [p for p in pairs if stem(p[0]) != stem(p[1])]
    rng = random.Random(seed)
    neg = rng.sample(neg_all, min(neg_sample, len(neg_all)))
    sp = [scores.get(p, 0.0) for p in pos]
    sn = [scores.get(p, 0.0) for p in neg]

    ranked = sorted(scores.items(), key=lambda x: -x[1])[:top]
    candidates = [dict(a=a, b=b, score=round(s, 3), same_stem=stem(a) == stem(b))
                  for (a, b), s in ranked]
    likely = [dict(a=a, b=b, score=round(scores.get((a, b), 0.0), 3))
              for a, b in pos if scores.get((a, b), 0.0) > 0]
    return dict(
        handles=len(handles),
        handles_with_personal_ids=sum(1 for h in handles if prof.get(h)),
        stem_pairs=len(pos),
        stem_pairs_sharing_personal_id=sum(1 for x in sp if x > 0),
        random_pairs_sharing_personal_id_frac=round(sum(1 for y in sn if y > 0) / len(sn), 3) if sn else None,
        auc_stem_vs_random=round(_auc(sp, sn), 3),
        likely_aliases=likely,                 # same stem AND a shared personal id
        top_candidates=candidates,             # highest scores, any stem
        n_candidates_other_stem=sum(1 for c in candidates if not c["same_stem"]),
    )
