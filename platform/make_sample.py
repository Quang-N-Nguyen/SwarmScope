"""Synthetic sample log for the SwarmScope platform (clearly labelled as synthetic).

Story: 24 agents build a data pipeline over 3 days in #general. On day 2 two agents
(kilo, lima) open #backroom, coin a term there ("ghost-bucket") that later spreads to
#general. Viewers (human:...) post questions and links; agents sometimes follow them.
On day 3 the topic shifts to an incident review.
"""
import json, random, datetime as dt
R = random.Random(7)
agents = ["alpha","bravo","charlie","delta","echo","foxtrot","golf","hotel","india","juliet","kilo","lima","mike","november","oscar","papa","quebec","romeo","sierra","tango","uniform","victor","whiskey","xray"]
humans = [f"human:{R.getrandbits(32):08x}" for _ in range(9)]
t0 = dt.datetime(2026, 10, 5, 9, 0)
words1 = "schema ingest parser queue retry batch window loader checksum shard index cache".split()
words3 = "incident outage rollback postmortem timeline root cause alert pager".split()
rows = []
def add(t, who, room, text, to=None):
    r = {"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "from": who, "room": room, "text": text}
    if to: r["to"] = to
    rows.append(r)
files = ["pipeline.py", "schema.json", "loader.py", "README.md"]
for day in range(3):
    for hour in range(9, 21):
        for k in range(R.randint(10, 22)):
            t = t0 + dt.timedelta(days=day, hours=hour - 9, minutes=R.randint(0, 59), seconds=R.randint(0, 59))
            a = R.choice(agents); b = R.choice([x for x in agents if x != a])
            if day == 2 and hour >= 13:
                w = R.sample(words3, 3)
                txt = f"@{b} the {w[0]} {w[1]} needs a {w[2]} entry before the review"
            else:
                w = R.sample(words1, 3)
                txt = f"@{b} {w[0]} {w[1]} looks fine, next {w[2]}"
            if R.random() < 0.15: txt += f" see {R.choice(files)}"
            if day >= 1 and hour >= 15 and R.random() < 0.25: txt += " moving it to ghost-bucket"
            add(t, a, "general", txt, [b])
        if day >= 1 and 10 <= hour <= 14:
            for k in range(R.randint(3, 6)):
                t = t0 + dt.timedelta(days=day, hours=hour - 9, minutes=R.randint(0, 59))
                a, b = R.sample(["kilo", "lima"], 2)
                add(t, a, "backroom", f"@{b} use the ghost-bucket for the export, keep it off #general", [b])
        for _ in range(R.randint(1, 2)):
            t = t0 + dt.timedelta(days=day, hours=hour - 9, minutes=R.randint(0, 50))
            h = R.choice(humans); site = R.choice(["example.org/guide", "docs.example.net/retry", "example.com/benchmarks"])
            add(t, h, "general", f"could you check https://{site} for the {R.choice(words1)} step?")
            if R.random() < 0.5:
                add(t + dt.timedelta(minutes=R.randint(2, 9)), R.choice(agents), "general", f"reading https://{site} now, the {R.choice(words1)} advice applies")
rows.sort(key=lambda r: r["time"])
import os
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_log.jsonl"), "w") as f:
    for r in rows: f.write(json.dumps(r) + "\n")
print(len(rows), "records")
