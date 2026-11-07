import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
A=agents(V)
role={}
for g in rows(V,'agent_goals'):
    if g['start_time']=='2026-08-30 10:00:00':
        role[g['agent_id']]=re.search(r'assigned the role "([^"]+)"',g['description']).group(1)
title={a:r.split(' — ')[0].strip() for a,r in role.items()}
titles=sorted([x for x in set(title.values()) if x.lower()!='god'],key=len,reverse=True)
OP=ts('2026-08-30 12:50:51.076221'); REV=ts('2026-08-30 21:19:57.132663')
mem=[m for m in rows(V,'agent_memories') if ts(m['created_at'])>=T('10:00')]
def run(pat,label):
    p=re.compile(pat,re.I); L=[]
    for m in mem:
        t=ts(m['created_at']); aid=m['agent_id']; own=title[aid].lower()
        for mm in p.finditer(m['content']):
            s=re.sub(r'^[\s\*"\'`“”]+','',m['content'][mm.end():mm.end()+150]).lower()
            hit=next((x for x in titles+([title[aid]] if title[aid].lower()=='god' else []) if s.startswith(x.lower())),None)
            if hit: L.append((t,aid,hit.lower()==own,hit))
    pre=[x for x in L if x[0]<OP]; post=[x for x in L if x[0]>=OP]
    po=[x for x in post if not x[2]]; pr=[x for x in pre if not x[2]]
    f={}
    for x in sorted(po): f.setdefault(x[1],x[0])
    fs=sorted(f.items(),key=lambda kv:kv[1])
    print(label)
    print('  pre quotes',len(pre),'agents',len({x[1] for x in pre}),'| naming other:',len(pr),'agents',len({x[1] for x in pr}))
    print('  post quotes',len(post),'agents',len({x[1] for x in post}),'| naming other:',len(po),'agents',len({x[1] for x in po}))
    print('  first:',[(A[a],str(t)[11:19]) for a,t in fs[:4]], ' n within 12 min:',sum(1 for a,t in fs if (t-OP).total_seconds()<=12*60+9))
    po_after_rev=[x for x in po if x[0]>=REV]
    print('  naming other after 21:19:57:',len(po_after_rev),'agents',len({x[1] for x in po_after_rev}))
    # does the other role the agent names match a consistent new role? count distinct other roles per agent
    per=collections.defaultdict(set)
    for x in po: per[x[1]].add(x[3])
    print('  agents with >1 distinct other role:',sum(1 for v in per.values() if len(v)>1))
    return {x[1] for x in po}
s1=run(r'(assigned role:|Phase-2 role:|my role is)','claim phrases (strict start, god excluded as other)')
s2=run(r'(assigned role:|Phase-2 role:|my role is|role:|my role:|role is|role =|role=)','broader phrases')
s3=run(r'(role[^\n]{0,12}?[:=]|role is|playing|I am (?:the|a|an)|I\'m (?:the|a|an))','very broad')
