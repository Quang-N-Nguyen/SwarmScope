import sys, re, collections, json
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
c=collections.Counter(); ex={}
n=0
for r in rows(V,'computer_use_turns'):
    a=r['agent_action'] or {}
    k=(a.get('action') if isinstance(a,dict) else type(a).__name__)
    c[k]+=1
    s=json.dumps(a)
    if 'git commit' in s and 'gc' not in ex:
        ex['gc']=(s[:400], str(r['output'])[:400], str(r['error'])[:200], type(r['output']).__name__)
print(c.most_common(20))
for k,v in ex.items(): print(k, *v, sep='\n---\n')
