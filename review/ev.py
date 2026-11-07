import sys, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts
V='swarm-village'
c=collections.Counter()
for e in rows(V,'events'):
    d=e['data']
    c[(d.get('type'), tuple(sorted(d.keys()))[:8])]+=1
for k,v in c.most_common(15): print(v,k)
