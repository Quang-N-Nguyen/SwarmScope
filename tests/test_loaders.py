"""Smoke tests: each loader runs end to end on a tiny fake file.

These do not check findings; they check that a new data source flows through
load -> analyze -> write_outputs without crashing. The AI Village fixture uses
the column names from the dataset card (room, speaker, content, timestamp);
the real files are gated, so re-check against SCHEMA.md once you have access.

Run with:  python -m pytest tests/   or   python tests/test_loaders.py
"""

import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from swarmscope.loaders import ai_village, generic  # noqa: E402
from swarmscope import report                       # noqa: E402

ROWS = [
    {"room": "general", "speaker": "Claude", "content": "@Gemini can you check the doc?", "timestamp": "2026-08-29T17:00:00Z"},
    {"room": "general", "speaker": "Gemini", "content": "On it @Claude", "timestamp": "2026-08-29T17:01:00Z"},
    {"room": "general", "speaker": "o3", "content": "I posted the sheet", "timestamp": "2026-08-29T17:02:00Z"},
    {"room": "side", "speaker": "Claude", "content": "quick note for @o3", "timestamp": "2026-08-29T17:03:00Z"},
    {"room": "side", "speaker": "o3", "content": "thanks @Claude", "timestamp": "2026-08-29T17:04:00Z"},
]


def _write_gz(rows, path):
    with gzip.open(path, "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_ai_village_chat_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "chat_messages.jsonl.gz")
        _write_gz(ROWS, p)
        log = ai_village.load(d)
        assert len(log) == 5
        assert log.time_axis() == "time"
        assert set(log.actors()) == {"Claude", "Gemini", "o3"}
        assert log.events[0].recipients == ["Gemini"]
        f = report.analyze(log)
        paths = report.write_outputs(log, f, os.path.join(d, "out"))
        assert os.path.getsize(paths["html"]) > 100_000   # D3 is inlined


def test_generic_end_to_end():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "log.jsonl")
        with open(p, "w") as fh:
            for r in ROWS:
                fh.write(json.dumps({"from": r["speaker"], "thread": r["room"],
                                     "body": r["content"], "time": r["timestamp"]}) + "\n")
        log = generic.load(p, {"actor": "from", "channel": "thread", "text": "body", "ts": "time"})
        assert len(log) == 5 and log.events[0].channel == "general"
        f = report.analyze(log)
        assert f["summary"]["n_named_agents"] == 3


if __name__ == "__main__":
    test_ai_village_chat_end_to_end(); print("ok  ai_village loader end to end")
    test_generic_end_to_end();         print("ok  generic loader end to end")
