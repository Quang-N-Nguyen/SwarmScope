import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
mem=list(rows(V,'agent_memories'))
print(len(mem), min(m['created_at'] for m in mem), max(m['created_at'] for m in mem))
print(collections.Counter(m['created_at'][:13] for m in mem))
p=r'(assigned role:|Play your assigned role:|Phase-2 role:|my role is)'
c=collections.Counter()
for m in mem:
    for mm in re.finditer(p,m['content'],re.I): c[mm.group(0).lower()]+=1
print(c)
lens=[len(m['content']) for m in mem]; print('len min/med/max',min(lens),sorted(lens)[len(lens)//2],max(lens))
