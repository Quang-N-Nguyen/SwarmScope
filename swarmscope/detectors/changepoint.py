"""Did something change? Online change-point detection on the real clock.

The question from the brief is whether a tool could flag trouble *early*. For
a whole swarm, trouble often shows up as a sudden change in what the agents
talk about (everyone starts discussing the same new problem) or in how much
they talk. This detector watches both, using only the past at every step:

1. Every ``step`` minutes, take the last ``window`` minutes of messages (W) and
   the ``baseline`` minutes before that (B).
2. **Topic shift** = Jensen-Shannon divergence between the word frequencies
   of W and B (0 = same words, 1 = no words in common), computed only when
   both windows hold enough messages.
3. **Volume change** = log ratio of W's message rate to B's.
4. Turn each into a robust z-score (median / MAD) against its own history so
   far (steps where either window is empty are skipped), and flag a step when either is >= ``z`` (volume: in either
   direction). After a flag, stay quiet for ``refractory`` minutes so one
   incident gives one alert.

We score the alerts against known milestones (for AI Village, the operator
messages): a milestone counts as *detected* if an alert fires within
``tolerance`` minutes after it; an alert that follows no milestone is a
*false alert*.

Small example: words in B = {build: 6, code: 4}, words in W = {role: 5,
build: 5}. They share only "build", so the divergence is high (about 0.45),
far above a typical step's 0.1-0.2, and the step is flagged.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional

from ..events import EventLog

_WORD = re.compile(r"[a-z][a-z_\-]{3,30}")


def _js(p: Counter, q: Counter) -> float:
    """Jensen-Shannon divergence (base 2, between 0 and 1) of two word counts."""
    sp, sq = sum(p.values()), sum(q.values())
    if not sp or not sq:
        return 0.0
    d = 0.0
    for w in set(p) | set(q):
        a, b = p.get(w, 0) / sp, q.get(w, 0) / sq
        m = (a + b) / 2
        if a:
            d += 0.5 * a * math.log2(a / m)
        if b:
            d += 0.5 * b * math.log2(b / m)
    return d


def _robust_z(hist: List[float], x: float, warmup: int) -> float:
    """z-score of x against past values, using median and MAD (robust to outliers)."""
    if len(hist) < warmup:
        return 0.0
    h = sorted(hist)
    med = h[len(h) // 2]
    mad = sorted(abs(v - med) for v in h)[len(h) // 2] * 1.4826
    if mad == 0:
        # More than half the past values are identical (sparse logs): fall back
        # to the mean absolute deviation; if that is 0 too, there is no spread
        # to compare with, so no alert. (A first version divided by 1e-9 and
        # gave z = 762,140,052 on the Transluce reports.)
        mad = sum(abs(v - med) for v in h) / len(h) * 1.2533
        if mad == 0:
            return 0.0
    return (x - med) / mad


def detect(log: EventLog, window: int = 30, baseline: int = 120, step: int = 10,
           z: float = 3.5, refractory: int = 120, warmup: int = 12, min_msgs: int = 20) -> dict:
    """Run the online detector. Times are in minutes.

    Two signals, each compared with the *recent* past (baseline B) and then
    z-scored against its own history (median / MAD, so one big burst does not
    hide the next one):

    * volume change  = log((messages in W + 1) / (expected from B + 1)), where
      expected = messages in B scaled to W's length. A surge after a lull
      gives a large positive value even if busier hours happened earlier.
    * topic shift    = Jensen-Shannon divergence of W vs B word counts, only
      when both have at least ``min_msgs`` messages (tiny samples always look
      different, which would make quiet hours look like topic shifts).
    """
    msgs = [(e.ts, Counter(_WORD.findall(e.meta.get("text_lc") or "")))
            for e in log.timed_events() if e.kind == "chat" and e.actor]
    if len(msgs) < 50:
        return dict(steps=0, alerts=[])
    t0, t1 = msgs[0][0], msgs[-1][0]
    W, B, S = window * 60, baseline * 60, step * 60
    js_hist: List[float] = []
    vol_hist: List[float] = []
    alerts, series = [], []
    last_alert = -1e18
    # Sliding windows: B = [t-W-B, t-W), W = [t-W, t). Three pointers move
    # forward only, adding and removing messages, so long logs stay fast.
    # Logs longer than 3 days usually follow a daily schedule (open-chat-village
    # runs weekdays 9am-5pm PT). There, compare each step with the same hour of
    # day on earlier days, so "the village opened" is not an alert.
    daily = (t1 - t0) > 3 * 86400
    hist_by_hour: Dict[int, List[float]] = {}
    cw, cb = Counter(), Counter()
    i_b0 = i_w0 = i_w1 = 0          # first msg in B, first msg in W, first msg after W
    n = len(msgs)
    t = t0 + W + B
    while t <= t1 + S:
        while i_w1 < n and msgs[i_w1][0] < t:           # enters W
            cw.update(msgs[i_w1][1]); i_w1 += 1
        while i_w0 < i_w1 and msgs[i_w0][0] < t - W:    # leaves W, enters B
            cw.subtract(msgs[i_w0][1]); cb.update(msgs[i_w0][1]); i_w0 += 1
        while i_b0 < i_w0 and msgs[i_b0][0] < t - W - B:  # leaves B
            cb.subtract(msgs[i_b0][1]); i_b0 += 1
        nw, nb = i_w1 - i_w0, i_w0 - i_b0
        if nw == 0 or nb == 0:
            # One window is empty: the log is closed (night, weekend) or just
            # reopening. Villages that run on a schedule (open-chat: weekdays
            # 9am-5pm) would otherwise alert at every opening and closing.
            t += S
            continue
        vol = math.log((nw + 1) / (nb * W / B + 1))
        js = _js(+cw, +cb) if (nw >= min_msgs and nb >= min_msgs) else None
        if daily:
            hh = hist_by_hour.setdefault(int(t // 3600) % 24, [])
            zv = _robust_z(hh, vol, 5)
            hh.append(vol)
        else:
            zv = _robust_z(vol_hist, vol, warmup)
        zj = _robust_z(js_hist, js, warmup) if js is not None else 0.0
        series.append(dict(t=t, n=nw, vol=round(vol, 3), js=(round(js, 4) if js is not None else None),
                           z_volume=round(zv, 2), z_topic=round(zj, 2)))
        if (zj >= z or abs(zv) >= z) and t - last_alert >= refractory * 60:
            why = "topic shift" if zj >= abs(zv) else ("volume surge" if zv > 0 else "volume drop")
            alerts.append(dict(t=t, why=why, z_topic=round(zj, 2), z_volume=round(zv, 2),
                               top_new_words=[w for w, _ in (+cw - +cb).most_common(6)]))
            last_alert = t
        vol_hist.append(vol)
        if js is not None:
            js_hist.append(js)
        if len(vol_hist) > 5000:          # keep history bounded on very long logs
            vol_hist = vol_hist[-5000:]
        if len(js_hist) > 5000:
            js_hist = js_hist[-5000:]
        t += S
    return dict(params=dict(window=window, baseline=baseline, step=step, z=z, refractory=refractory,
                            min_msgs=min_msgs, daily_baseline=daily),
                steps=len(series), alerts=alerts, series=series)


def score(alerts: List[dict], milestones: Dict[str, float], labels: Dict[str, str],
          t_start: float, tolerance: int = 90) -> dict:
    """Match alerts to milestones: detection delay per milestone, false alerts."""
    tol = tolerance * 60
    ms = sorted(((k, v) for k, v in milestones.items() if v > t_start), key=lambda x: x[1])
    rows, used = [], set()
    for k, v in ms:
        hit = next((a for a in alerts if v <= a["t"] <= v + tol), None)
        if hit:
            used.add(id(hit))
        rows.append(dict(milestone=k, label=labels.get(k, k), ts=v, detected=bool(hit),
                         delay_minutes=round((hit["t"] - v) / 60, 1) if hit else None))
    false_alerts = [a for a in alerts if id(a) not in used and
                    not any(v <= a["t"] <= v + tol for _, v in ms)]
    return dict(tolerance_minutes=tolerance, milestones=rows,
                detected=sum(1 for r in rows if r["detected"]), total=len(rows),
                false_alerts=len(false_alerts),
                false_alert_times=[a["t"] for a in false_alerts])


def corroborate(log: EventLog, alerts: List[dict], after: int = 30, before: int = 120,
                min_events: int = 20, ratio: float = 3.0) -> None:
    """Check each alert against the log's non-chat actions (pauses, memory
    updates, searches...). An alert is *corroborated* when some action type's
    rate in the ``after`` minutes following it differs from the ``before``
    minutes preceding it by ``ratio`` times or more (with at least
    ``min_events`` events). This is independent evidence, because the
    detector itself only reads chat.
    """
    acts = [(e.ts, e.kind) for e in log.timed_events() if e.kind != "chat"]
    for a in alerts:
        t = a["t"]
        pre = Counter(k for ts, k in acts if t - before * 60 <= ts < t)
        post = Counter(k for ts, k in acts if t <= ts < t + after * 60)
        found = []
        for k in sorted(set(pre) | set(post)):
            r_pre = pre.get(k, 0) / before
            r_post = post.get(k, 0) / after
            if pre.get(k, 0) + post.get(k, 0) < min_events:
                continue
            if r_post >= ratio * max(r_pre, 1e-9) or r_pre >= ratio * max(r_post, 1e-9):
                found.append(f"{k} {'up' if r_post > r_pre else 'down'} "
                             f"{r_pre * 60:.0f}->{r_post * 60:.0f}/h")
        a["corroborated_by"] = found


def daily_topic(log: EventLog, z: float = 2.5, ref_days: int = 3, lag: int = 2, min_msgs: int = 50) -> dict:
    """Slow version for long logs: did today's words differ from the last few days?

    Each active day (>= ``min_msgs`` agent messages) is compared with the
    previous ``ref_days`` active days (Jensen-Shannon divergence), z-scored
    against earlier days (median / MAD). A milestone counts as *flagged* when
    one of its first ``lag`` active days alerts. ``chance`` is the same rate
    for every active day, so recall can be compared with it.

    Example (main-village, 421 active days, 50 goal changes): 36% of goal
    changes flagged vs 8% of all days, with 20 alert days.
    """
    day: Dict[int, Counter] = {}
    n: Counter = Counter()
    for e in log.timed_events():
        if e.kind == "chat" and e.actor and not e.actor.startswith("human:"):
            d = int(e.ts // 86400)
            day.setdefault(d, Counter()).update(_WORD.findall(e.meta.get("text_lc") or ""))
            n[d] += 1
    days = sorted(d for d in day if n[d] >= min_msgs)
    if len(days) < ref_days + 10:
        return {}
    zs, hist = {}, []
    for i, d in enumerate(days):
        if i < ref_days:
            continue
        base = Counter()
        for dd in days[i - ref_days:i]:
            base.update(day[dd])
        js = _js(day[d], base)
        zs[d] = _robust_z(hist, js, 10)
        hist.append(js)
    alert_days = [d for d in days if zs.get(d, 0) >= z]

    def flagged(d0):
        return any(zs.get(x, 0) >= z for x in [x for x in days if x >= d0][:lag])

    out = dict(params=dict(z=z, ref_days=ref_days, lag=lag, min_msgs=min_msgs),
               active_days=len(days), alert_days=[d * 86400 + 43200 for d in alert_days],
               series=[(d * 86400 + 43200, round(zs[d], 2)) for d in days if d in zs],
               chance=round(sum(flagged(d) for d in days) / len(days), 3))
    ms = getattr(log, "milestones", {}) or {}
    if ms:
        first = min(ms.values())
        md = [int(v // 86400) for v in ms.values() if v > first]
        hit = sum(flagged(d) for d in md)
        # precision: alert days that fall on one of a milestone's first `lag` active days
        windows = set()
        for m in md:
            windows.update([x for x in days if x >= m][:lag])
        out.update(milestones=len(md), flagged=hit, recall=round(hit / len(md), 3) if md else None,
                   precision=round(sum(1 for a in alert_days if a in windows) / len(alert_days), 3) if alert_days else None)
    return out


def run_all(log: EventLog, **kw) -> dict:
    if not any(e.kind == "chat" and e.meta.get("text_lc") for e in log.events):
        return {}
    d = detect(log, **kw)
    ms = getattr(log, "milestones", {}) or {}
    timed = log.timed_events()
    if ms and timed and d.get("alerts") is not None:
        # The first milestone is the start of the log, which cannot be detected online.
        first = min(ms.values())
        d["score"] = score(d["alerts"], {k: v for k, v in ms.items() if v > first},
                           getattr(log, "milestone_labels", {}) or {}, timed[0].ts)
    timed_ = log.timed_events()
    if timed_ and timed_[-1].ts - timed_[0].ts > 7 * 86400:
        d["daily"] = daily_topic(log)
    if d.get("alerts"):
        corroborate(log, d["alerts"])
        if "score" in d:
            fa = set(d["score"]["false_alert_times"])
            d["score"]["unlabeled_but_corroborated"] = sum(
                1 for a in d["alerts"] if a["t"] in fa and a.get("corroborated_by"))
            d["score"]["unexplained"] = sum(
                1 for a in d["alerts"] if a["t"] in fa and not a.get("corroborated_by"))
    return d
