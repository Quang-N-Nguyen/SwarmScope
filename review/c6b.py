import sys, re, collections, random
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
A=agents(V)
mem=list(rows(V,'agent_memories'))
p=r'(assigned role:|Phase-2 role:|my role is)'
random.seed(1)
ex=[]
for m in mem:
    for mm in re.finditer(p,m['content'],re.I):
        ex.append((m['created_at'][11:16], A[m['agent_id']], m['content'][mm.start():mm.end()+90].replace('\n',' | ')))
for e in random.sample(ex,25): print(e)
