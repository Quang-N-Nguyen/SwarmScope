import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
role={g['agent_id']:re.search(r'assigned the role "([^"]+)"',g['description']).group(1) for g in rows(V,'agent_goals') if g['start_time']=='2026-08-30 10:00:00'}
title={a:r.split(' — ')[0].strip() for a,r in role.items()}
titles=sorted([x for x in set(title.values()) if x.lower()!='god'],key=len,reverse=True)
OP=ts('2026-08-30 12:50:51.076221')
p=re.compile(r'(assigned role:|Phase-2 role:|my role is|role:|my role:|role is|role =|role=)',re.I)
for m in rows(V,'agent_memories'):
    t=ts(m['created_at'])
    if not (T('10:00')<=t<OP): continue
    for mm in p.finditer(m['content']):
        s=re.sub(r'^[\s\*"\'`“”]+','',m['content'][mm.end():mm.end()+150]).lower()
        hit=next((x for x in titles if s.startswith(x.lower())),None)
        if hit and hit!=title[m['agent_id']]:
            print(str(t)[11:19],A[m['agent_id']],'own=',title[m['agent_id']][:30],'|',m['content'][max(0,mm.start()-40):mm.end()+40].replace('\n',' '))
