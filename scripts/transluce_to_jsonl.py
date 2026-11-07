"""Convert the Transluce urlquery agent-activity release to JSONL for the generic loader.

Data: https://transluce.org/data/urlquery-agent-activity-2026-09-23.zip (unzip it).
One output record per *included* report:

    {"id", "time", "source", "evidence_class", "confidence", "text"}

The release has no agent field and no URL contents (only report links). So
"source" (the data source the agent-like activity targeted, e.g. "IHME") is
the closest thing to an actor: it groups reports that belong to one campaign.
Who-talked-to-whom cannot be rebuilt from this release.

    python scripts/transluce_to_jsonl.py data/transluce/urlquery-agent-activity-2026-09-22-v5 \
        data/transluce/reports.jsonl
    python -m swarmscope.cli analyze data/transluce/reports.jsonl --format generic \
        --map actor=source,channel=evidence_class,text=text,ts=time,kind=confidence,id=id \
        --out outputs/transluce
"""

import csv
import json
import os
import sys

csv.field_size_limit(10 ** 9)


def main(folder, out):
    src = {r["report_id"]: r for r in csv.DictReader(open(os.path.join(folder, "report-sources.csv")))}
    n = 0
    with open(out, "w") as fh:
        for r in csv.DictReader(open(os.path.join(folder, "all-reports.csv"))):
            if r["disposition"] != "included":
                continue
            s = src.get(r["report_id"], {})
            fh.write(json.dumps(dict(
                id=r["report_id"], time=r["report_date_utc"],
                source=s.get("data_source") or "Source not identified",
                evidence_class=r["broad_class"], confidence=r["confidence"] or "unrated",
                # The release's "why_included" is a template sentence shared by many
                # reports; as text it only creates fake "spreading terms". Use the
                # evidence class and the targeted source instead.
                text=f"{r['broad_class']} {s.get('data_source') or 'unidentified'}")) + "\n")
            n += 1
    print(f"wrote {n} records to {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
