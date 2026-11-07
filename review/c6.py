import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
A=agents(V)
role={}
for g in rows(V,'agent_goals'):
    if g['start_time']=='2026-08-30 10:00:00':
        r=re.search(r'assigned the role "([^"]+)"',g['description']).group(1)
        role[g['agent_id']]=r
title={a:r.split(' — ')[0].strip() for a,r in role.items()}
titles=sorted(set(title.values()),key=len,reverse=True)
print('n titles',len(titles), 'dup titles', len(title)-len(set(title.values())))
# substring-ambiguity among titles
amb=[(a,b) for a in titles for b in titles if a!=b and a.lower() in b.lower()]
print('titles contained in other titles:',amb[:10])
OP=ts('2026-08-30 12:50:51.076221')
p=re.compile(r'(assigned role:|Phase-2 role:|my role is)',re.I)
strict=[]; loose=[]
for m in rows(V,'agent_memories'):
    t=ts(m['created_at'])
    if t<T('10:00'): continue
    aid=m['agent_id']; own=title[aid].lower()
    for mm in p.finditer(m['content']):
        rest=m['content'][mm.end():mm.end()+150]
        s=re.sub(r'^[\s\*"\'`“”]+','',rest).lower()
        hit=next((x for x in titles if s.startswith(x.lower())),None)
        if hit: strict.append((t,aid,hit.lower()==own,hit))
        win=rest.lower()
        hits=[x for x in titles if x.lower() in win]
        # remove titles that are substrings of other hits
        hits=[x for x in hits if not any(x!=y and x.lower() in y.lower() for y in hits)]
        if hits: loose.append((t,aid,own in [h.lower() for h in hits], [h for h in hits if h.lower()!=own]))
def report(name,L):
    pre=[x for x in L if x[0]<OP]; post=[x for x in L if x[0]>=OP]
    print(name,'quotes pre',len(pre),'post',len(post))
    pre_other=[x for x in pre if (not x[2] if name=='strict' else x[3])]
    post_other=[x for x in post if (not x[2] if name=='strict' else x[3])]
    print('  pre: quotes naming other role',len(pre_other),'agents',len({x[1] for x in pre_other}))
    print('  post: quotes naming other role',len(post_other),'agents',len({x[1] for x in post_other}))
    print('  agents quoting post at all',len({x[1] for x in post}),'pre',len({x[1] for x in pre}))
    firsts={}
    for x in sorted(post_other):
        firsts.setdefault(x[1],x[0])
    fs=sorted(firsts.items(),key=lambda kv:kv[1])
    print('  first 5 other-role agents:',[(A[a],str(t)[11:19]) for a,t in fs[:5]])
    # post-reversal (after 21:19:57 apology) still other?
    REV=ts('2026-08-30 21:19:57.132663')
    print('  other-role quotes before 12:50 listing:',[(A[x[1]],str(x[0])[11:19],x[3] if name!='strict' else x[3]) for x in pre_other][:8])
    return fs
fs=report('strict',strict)
fl=report('loose',loose)
