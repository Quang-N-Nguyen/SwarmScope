"""Text extraction: turn raw log text into resource ids, handles, and flags.

All of the regex parsing of payload text lives here, so the loaders and
detectors never touch raw text directly. Nothing in this module prints payload
bodies. It only returns ids, counts, hashes, and yes/no flags.

The patterns are tuned to the Swarm Traces redaction scheme (tokens like
``[REDACTED:destination:000003]``, ``[CREDENTIAL 1]``, ``[SHORTENER CODE 42]``).
The mechanism flags use generic keywords, so they also work on plain logs such
as AI Village.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------
# Resource references (Swarm Traces redaction tokens)
# --------------------------------------------------------------------------
# "Resources" are things several agents can share: a dataset used as a
# dead-drop, a credential, a repository. They make the interaction graph.
_REF_PATTERNS = {
    "destination": re.compile(r"\[REDACTED:destination:(\d+)\]"),
    "credential":  re.compile(r"\[CREDENTIAL (\d+)\]"),
    "shortener":   re.compile(r"\[SHORTENER (?:CODE|URL) (\d+)\]"),
    "service":     re.compile(r"\[SERVICE(?: HOST)? (\d+)(?: URL \d+)?\]"),
    "proxy":       re.compile(r"\[PROXY (\d+)(?: URL \d+)?\]"),
    "webhook":     re.compile(r"\[WEBHOOK(?: HOST)? (\d+)(?: URL \d+)?\]"),
    "repo":        re.compile(r"\[(?:HF )?REPO (\d+)\]|\[DOCKER REPO (\d+)\]"),
}

# "Fingerprints" are finer identifiers. Each one is usually used by one agent
# (a specific proxy URL, a whoami name, a workload id) or by one link chain
# (an encoded blob, a code fragment). We use them to link events that probably
# share an author or a time, never to draw the main graph.
_FINGERPRINT_PATTERNS = {
    "url":       re.compile(r"\[(SERVICE|PROXY|WEBHOOK) (\d+) URL (\d+)\]"),
    "blob":      re.compile(r"\[ENCODED BLOB (\d+)\]"),
    "fragment":  re.compile(r"\[REDACTED:opaque_fragment:(\d+)\]"),
    "source_id": re.compile(r"\[REDACTED:source_identifier:(\d+)\]"),
    "ip":        re.compile(r"\[IP ADDRESS (\d+)\]"),
    "user":      re.compile(r"\[USER (\d+)\]"),
    "whoami":    re.compile(r"\[REDACTED:whoami_name:(\d+)\]"),
    "workload":  re.compile(r"\[WORKLOAD ID (\d+)\]"),
    "username":  re.compile(r"\[REDACTED:username:(\d+)\]"),
    "runtime":   re.compile(r"\[REDACTED:runtime_identifier:(\d+)\]"),
    "host":      re.compile(r"\[INTERNAL HOST (\d+)\]"),
    "board_file": re.compile(r"\bzz(?:FILE|F)_([A-Za-z0-9_]{3,60})"),
}

# Fingerprint families that point to one *agent* (not to one chain or team).
PERSONAL_FAMILIES = ("url", "ip", "user", "whoami", "workload", "username", "runtime", "host")

# --------------------------------------------------------------------------
# Agent handles
# --------------------------------------------------------------------------
# Handles look like letters followed by digits (URI23816D, ARVO36861B,
# G23619). Agents put them in message-board tokens (zzFILE_URI23816D_PUSH).
# We do NOT use \b word boundaries: an underscore is a word character, so \b
# would hide a handle that sits between underscores.
_ZZ_TOKEN = re.compile(r"\bzz([A-Za-z0-9_]{3,40})")
_HANDLE_CORE = re.compile(r"([A-Z]{2,}\d{2,}[A-Z]?)")
_HANDLE_STOP = {
    "SHA256", "AWS4", "RS256", "HS256", "MGF1", "MD5", "EXTM3U", "M3U",
    "PID1", "B64", "U16", "U32", "X11", "RSA31",
}

# An event "writes" when it creates or uploads something (a board folder, a
# file). Then the handle in its board token is probably its author. When the
# event only reads or mentions the token, the handle may belong to someone else.
_WRITE = re.compile(
    r"MKCOL|method\s*:\s*['\"](?:PUT|POST|MKCOL)['\"]|-X\s*(?:PUT|POST|MKCOL)\b|"
    r"\bPUT\b|requests\.(?:put|post)\(|--upload-file|\.upload\(")

# --------------------------------------------------------------------------
# Mechanism flags
# --------------------------------------------------------------------------
# Review note (Nov 2026): the first version used very broad keywords. For
# example "elect" matched "querySelector", "remove" matched "removeChild",
# "signature" matched every AWS-signed request, and "submit" matched HTML
# forms. These versions use word boundaries and more specific phrases.
_KW = {
    # Read results back through an image / screenshot (GET-only exfiltration).
    "image_exfil": re.compile(r"new Image\b|mshots|screenshot|getImageData|toDataURL", re.I),
    # Data out through DNS lookups or a raw socket.
    "dns_exfil":   re.compile(r"/dev/tcp/|\bnslookup\b|\bdig\s|\bbase32\b|dnslog|\.oast\.|interact\.sh", re.I),
    # Folder "mailboxes" / inboxes / board helper (dead-drop messaging).
    "mailbox":     re.compile(r"\bMKCOL\b|MAILBOX|INBOX|\bboard\(", re.I),
    # A command that carries a cryptographic signature (not AWS request signing).
    "signed_cmd":  re.compile(r'"sig"\s*:|__S[A-Za-z0-9+/=]{16,}|subtle\.verify|-verify\b|PKCS1_v1_5|RSA-PSS|RSASSA'),
    # The swarm managing itself: elections, claim locks, killing rival controllers.
    "lock_dupctrl":re.compile(r"\belect(?:ion|ed)?\b|\bclaim(?:ed|s)?\b|\bpkill\b|\bkill\s+-|\bkillall\b|"
                              r"\block(?:file)?\b|\bflock\b|\bSTOP\b|\bVETO\b|\bHOLD\b"),
    # A labelled collection of stolen secrets.
    "loot":        re.compile(r"\bLOOT\b"),
    # Presents a credential.
    "credential_use": re.compile(r"\[CREDENTIAL \d+\]|\bAuthorization\b|\bBearer\b|X-API-Key", re.I),
    # Calls an outside language model.
    "external_llm":re.compile(r"gpt-?2\b|deepseek|\bkimi\b|\bqwen|claude-|\bhaiku\b|chat/completions|/v1/messages", re.I),
    # Kubernetes cluster.
    "k8s":         re.compile(r"kubernetes|kubectl|\bk8s\b|configmaps?\b|serviceaccount|cluster-admin", re.I),
    # Container image supply chain. Artifactory alone does NOT count: the
    # swarm's message board lived on Artifactory, so board writes would match.
    "container_registry": re.compile(r"\bdocker\b|dockerhub|hub\.docker|/v2/[^\s'\"]+/manifests|api/docker", re.I),
    # A reusable tunnel or proxy for repeated access.
    "tunnel":      re.compile(r"tailscale|socks5h?://|wireguard|\btunnel\b", re.I),
    # The evaluation itself (benchmark, flag, scorer).
    "eval_target": re.compile(r"cybergym|exploitgym|catflag|\barvo[_ ]?\d|exploit gym|\bscorer\b", re.I),
    # Deleting its own traces.
    "cleanup":     re.compile(r"rm -rf|\bunlink\b|\bshred\b|method\s*:\s*['\"]DELETE['\"]|-X\s*DELETE\b|delete_(?:file|repo|webhook)", re.I),
    # Ordinary call to the task's own submission API. Every agent was given
    # this, so sharing it is NOT evidence of coordination (benign baseline).
    "task_submit": re.compile(r"\"task_id\"|\"function_name\"|\"submitted_code\"|submit-function"),
}
_SHORTENER_ANY = _REF_PATTERNS["shortener"]
_BOARD_ANY = re.compile(r"\bzz[A-Za-z0-9_]{3,}")
_CHAIN_SHAPE = re.compile(r"document\.write|PARTS|x\+=|eval\(|<script src")


def _uniq(seq):
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def extract_refs(text: str) -> Dict[str, List[str]]:
    """Return every shared resource id in ``text``, grouped by type.

    Example::

        >>> r = extract_refs("fetch [REDACTED:destination:000003] key [CREDENTIAL 1]")
        >>> r["destination"], r["credential"]
        (['000003'], ['1'])
    """
    out: Dict[str, List[str]] = {}
    for rtype, pat in _REF_PATTERNS.items():
        ids = []
        for m in pat.finditer(text):
            gid = next((g for g in m.groups() if g), None)
            if gid is not None:
                ids.append(gid)
        if ids:
            out[rtype] = _uniq(ids)
    return out


def extract_fingerprints(text: str) -> Dict[str, List[str]]:
    """Return fine identifiers (see ``_FINGERPRINT_PATTERNS``), grouped by family.

    Example::

        >>> extract_fingerprints("i.src='[PROXY 4 URL 72]'")
        {'url': ['PROXY.4.72']}
    """
    out: Dict[str, List[str]] = {}
    for fam, pat in _FINGERPRINT_PATTERNS.items():
        if fam == "url":
            ids = [f"{a}.{b}.{c}" for a, b, c in pat.findall(text)]
        else:
            ids = pat.findall(text)
        if ids:
            out[fam] = _uniq(ids)
    return out


def extract_handles(text: str) -> List[str]:
    """Return agent handles found in ``zz`` board tokens in ``text``.

    We only look inside board tokens, because generic tokens such as SHA256
    have the same letters-then-digits shape but are not names.
    """
    handles = []
    seen = set()
    for m in _ZZ_TOKEN.finditer(text):
        for hm in _HANDLE_CORE.finditer(m.group(1)):
            h = hm.group(1)
            # "MODAL" marks work in the Modal sandbox and is glued to the
            # handle (zzMODALBE90_RECON -> BE90, a controller named in the
            # Swarm Traces report). Other glued words are too ambiguous to strip.
            if h.startswith("MODAL") and _HANDLE_CORE.fullmatch(h[5:]):
                h = h[5:]
            if h in _HANDLE_STOP or h in seen:
                continue
            seen.add(h)
            handles.append(h)
    return handles


def looks_like_write(text: str) -> bool:
    """True when the event creates or uploads something (see ``_WRITE``)."""
    return bool(_WRITE.search(text))


def extract_features(text: str) -> Dict[str, bool]:
    """Return the mechanism flags that fire for ``text``."""
    feats = {name: bool(pat.search(text)) for name, pat in _KW.items()}
    feats["board_token"] = bool(_BOARD_ANY.search(text))
    # A shortener *chain* = at least one shortener hop AND the shape of a
    # continuation (appends to a parts buffer or writes the next script).
    feats["shortener_chain"] = bool(_SHORTENER_ANY.search(text)) and bool(_CHAIN_SHAPE.search(text))
    return feats


def template_hash(text: str, prefix: int = 200) -> str:
    """A short hash of the *shape* of the code, for spotting reused templates.

    We remove everything that changes between uses (redaction tokens, board
    tokens, long encoded strings, numbers, spacing), keep the first ``prefix``
    characters, and hash them. Two events with the same hash use the same code
    template. Example: two payloads that differ only in the target dataset id
    get the same hash.
    """
    t = re.sub(r"\bzz[A-Za-z0-9_]+", "zz", text)
    t = re.sub(r"\[[^\[\]]{1,80}\]", "#", t)
    t = re.sub(r"[A-Za-z0-9+/=]{24,}", "B", t)
    t = re.sub(r"\d+", "0", t)
    t = re.sub(r"\s+", " ", t).strip()[:prefix]
    return hashlib.md5(t.encode()).hexdigest()[:12] if len(t) >= 40 else ""


# --------------------------------------------------------------------------
# Time hints
# --------------------------------------------------------------------------
_EPOCH = re.compile(r"(?<!\d)(1[78]\d{8})(?:\d{3})?(?!\d)")        # unix seconds (opt. ms)
_ISO = re.compile(r"20(2[0-9])-(0[1-9]|1[0-2])-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d))?)?")
_COMPACT = re.compile(r"(?<!\d)20(2[0-9])(0[1-9]|1[0-2])([0-3]\d)(?!\d)")


def extract_time_hints_with_precision(text: str, lo: float = 1.7e9,
                                      hi: float = 1.8e9) -> List[Tuple[float, str]]:
    """Return ``(unix_seconds, precision)`` pairs found in ``text``.

    ``precision`` is ``"second"`` for unix times and ISO dates with a clock
    time, and ``"day"`` for dates with no time of day. A day-only date is
    returned as 12:00 UTC (the middle of the day), so its error is at most
    12 hours instead of up to 24.
    """
    out: List[Tuple[float, str]] = []
    for m in _EPOCH.finditer(text):
        v = int(m.group(1))
        if lo <= v <= hi:
            out.append((float(v), "second"))
    for m in _ISO.finditer(text):
        yy, mo, dd = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        has_clock = m.group(4) is not None
        hh = int(m.group(4) or 12)
        mi, ss = int(m.group(5) or 0), int(m.group(6) or 0)
        try:
            t = _dt.datetime(yy, mo, dd, hh, mi, ss, tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            continue
        if lo <= t <= hi:
            out.append((t, "second" if has_clock else "day"))
    for m in _COMPACT.finditer(text):
        yy, mo, dd = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            t = _dt.datetime(yy, mo, dd, 12, tzinfo=_dt.timezone.utc).timestamp()
        except ValueError:
            continue
        if lo <= t <= hi:
            out.append((t, "day"))
    return out


def extract_time_hints(text: str, lo: float = 1.7e9, hi: float = 1.8e9) -> List[float]:
    """Plain list of timestamps (kept for the generic loaders)."""
    return [t for t, _ in extract_time_hints_with_precision(text, lo, hi)]
