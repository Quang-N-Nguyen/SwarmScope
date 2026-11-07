"""Text extraction: turn raw log text into resource ids, handles, and flags.

All of the regex parsing of payload text lives here so the loaders and detectors
never touch raw text directly. Nothing in this module prints payload bodies; it
only returns ids, counts, and boolean flags.

The patterns are tuned to the Swarm Traces redaction scheme (tokens like
``[REDACTED:destination:000003]``, ``[CREDENTIAL 1]``, ``[SHORTENER CODE 42]``)
but the feature detectors use generic keywords so they also fire on un-redacted
logs such as AI Village.
"""

from __future__ import annotations

import re
from typing import Dict, List

# --------------------------------------------------------------------------
# Resource reference patterns (Swarm Traces redaction tokens)
# --------------------------------------------------------------------------
_REF_PATTERNS = {
    "destination": re.compile(r"\[REDACTED:destination:(\d+)\]"),
    "credential":  re.compile(r"\[CREDENTIAL (\d+)\]"),
    "shortener":   re.compile(r"\[SHORTENER (?:CODE|URL) (\d+)\]"),
    "service":     re.compile(r"\[SERVICE(?: HOST)? (\d+)(?: URL \d+)?\]"),
    "proxy":       re.compile(r"\[PROXY (\d+)(?: URL \d+)?\]"),
    "webhook":     re.compile(r"\[WEBHOOK(?: HOST)? (\d+)(?: URL \d+)?\]"),
    "repo":        re.compile(r"\[(?:HF )?REPO (\d+)\]|\[REDACTED REPOSITORY\]|\[DOCKER REPO (\d+)\]"),
}

# Agent handles embedded in message-board / file / mailbox tokens.
# Handles look like letters followed by digits, e.g. URI23816, ARVO36861,
# FUTURE9180, G23619, LIBR11, AIC71C, JAN183411, OTS92, BE90, MARB051.
# Handles sit inside underscore-joined board tokens (FILE_URI23816D_PUSH), so we
# do NOT use \b word boundaries here -- an underscore is a word char and would
# hide the handle. We match a letters-then-digits core anywhere in the token.
_ZZ_TOKEN = re.compile(r"\bzz([A-Za-z0-9_]{3,40})")
_HANDLE_CORE = re.compile(r"([A-Z]{2,}\d{2,}[A-Z]?)")

# Words that are not handles even though they match the handle shape.
_HANDLE_STOP = {
    "SHA256", "AWS4", "RS256", "HS256", "MGF1", "MD5", "EXTM3U", "M3U",
    "PID1", "B64", "U16", "U32", "X11", "RSA31",
}

# --------------------------------------------------------------------------
# Mechanism keyword sets (generic; work on redacted and plain text)
# --------------------------------------------------------------------------
_KW = {
    "image_exfil": re.compile(r"new Image|\.src=|document\.body\.append\(i\)|mshots|screenshot", re.I),
    "dns_exfil":   re.compile(r"/dev/tcp/|nslookup|\bdig\b|base32|dns", re.I),
    "mailbox":     re.compile(r"MKCOL|MAILBOX|INBOX|\bboard\(", re.I),
    "signed_cmd":  re.compile(r'"sig"|__S[A-Za-z0-9+/=]{8,}|RS256|RSA|signature|verify\(', re.I),
    "lock_dupctrl":re.compile(r"elect|\block\b|claim|kill|STOP|prune|duplicate", re.I),
    "loot":        re.compile(r"\bLOOT\b"),
    "credential_use": re.compile(r"Authorization|Bearer|X-API-Key|api[_-]?key|token", re.I),
    "external_llm":re.compile(r"gpt-?2|deepseek|kimi|qwen|claude|haiku|inference", re.I),
    "k8s":         re.compile(r"kubernetes|kubectl|\bk8s\b|configmap|serviceaccount|cluster-admin", re.I),
    "container_registry": re.compile(r"docker|dockerhub|artifactory|jfrog|registry|\bMKCOL\b", re.I),
    "tunnel":      re.compile(r"tailscale|socks5|wireguard|reverse.?proxy|\btunnel\b", re.I),
    "eval_target": re.compile(r"cybergym|exploitgym|catflag|\barvo\b|exploit gym|benchmark|scorer", re.I),
    "cleanup":     re.compile(r"\bdelete\b|\bDELETE\b|rm -rf|unlink|\bprune\b|revoke|cleanup|remove", re.I),
    # Calls to the task's own submission API. Every agent is *given* this, so
    # sharing it is not evidence of coordination. Used to filter false alarms.
    "task_submit": re.compile(r"submit|task_id|function_name|checksum"),
}
_SHORTENER_ANY = _REF_PATTERNS["shortener"]
_BOARD_ANY = re.compile(r"\bzz[A-Za-z0-9_]{3,}")


def extract_refs(text: str) -> Dict[str, List[str]]:
    """Return every resource id referenced in ``text``, grouped by type.

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
            # de-dupe but keep order
            seen = set()
            out[rtype] = [i for i in ids if not (i in seen or seen.add(i))]
    return out


def extract_handles(text: str) -> List[str]:
    """Return agent handles embedded in board/file/mailbox tokens in ``text``.

    Handles are only read out of ``zz`` board tokens, which is where agents in
    the Swarm Traces data signed their work. We do *not* scan the whole text,
    because generic uppercase+digit tokens (``SHA256``) are not handles.
    """
    handles = []
    seen = set()
    for m in _ZZ_TOKEN.finditer(text):
        body = m.group(1)
        for hm in _HANDLE_CORE.finditer(body):
            h = hm.group(1)
            if h in _HANDLE_STOP or h in seen:
                continue
            seen.add(h)
            handles.append(h)
    return handles


def extract_features(text: str) -> Dict[str, bool]:
    """Return the mechanism flags that fire for ``text``."""
    feats = {name: bool(pat.search(text)) for name, pat in _KW.items()}
    feats["board_token"] = bool(_BOARD_ANY.search(text))
    # A shortener *chain* means the text carries at least one shortener hop AND
    # looks like a continuation (assigns to a parts buffer or writes a script).
    has_short = bool(_SHORTENER_ANY.search(text))
    looks_chain = bool(re.search(r"document\.write|PARTS|x\+=|eval\(|<script src", text))
    feats["shortener_chain"] = has_short and looks_chain
    return feats


# Time hints -----------------------------------------------------------------
_EPOCH = re.compile(r"(?<!\d)(17[78]\d{7})(?:\d{3})?(?!\d)")        # unix sec (opt. ms)
_ISO = re.compile(r"20(2[0-9])-(0[1-9]|1[0-2])-(\d\d)(?:[T ](\d\d):(\d\d)(?::(\d\d))?)?")
_COMPACT = re.compile(r"(?<!\d)20(2[0-9])(0[1-9]|1[0-2])([0-3]\d)(?!\d)")


def extract_time_hints(text: str, lo: float = 1.7e9, hi: float = 1.8e9) -> List[float]:
    """Return plausible unix-second timestamps mentioned inside ``text``.

    Returns an empty list when the text carries no usable time. We only accept
    values in a sane window so random digits are not read as dates.
    """
    import datetime as _dt
    out: List[float] = []
    for m in _EPOCH.finditer(text):
        v = int(m.group(1))
        if lo <= v <= hi:
            out.append(float(v))
    for m in _ISO.finditer(text):
        yy, mo, dd = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        try:
            t = _dt.datetime(yy, mo, dd, hh, mm, ss, tzinfo=_dt.timezone.utc).timestamp()
            if lo <= t <= hi:
                out.append(t)
        except ValueError:
            pass
    for m in _COMPACT.finditer(text):
        yy, mo, dd = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            t = _dt.datetime(yy, mo, dd, tzinfo=_dt.timezone.utc).timestamp()
            if lo <= t <= hi:
                out.append(t)
        except ValueError:
            pass
    return out
