import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
msgs = sorted(rows(V,'chat_messages'), key=lambda m: ts(m['created_at']))
op=ts('2026-08-30 12:50:51.076221'); d=T('15:23')-T('12:50')
p=r'new role|reassign|my role|role[ -]?(?:changed|shuffled|change|shuffle|swap)'
c=collections.Counter()
for m in msgs:
    t=ts(m['created_at'])
    if m['speaker_type']=='agent' and op-d<=t<op:
        for mm in re.finditer(p,m['content'],re.I): c[mm.group(0).lower()]+=1
        mm=re.search(p,m['content'],re.I)
        if mm: print(m['created_at'][11:19], m['content'][max(0,mm.start()-50):mm.end()+30].replace('\n',' '))
print(c)
# also: any mention of shuffle/label/goal changed in whole post-op period
q=r'shuffl|reshuffl|label|goal (?:changed|says)|role (?:label|mismatch)|different role|wrong role'
for m in msgs:
    t=ts(m['created_at'])
    if m['speaker_type']=='agent' and t>=op and re.search(q,m['content'],re.I):
        mm=re.search(q,m['content'],re.I)
        print('POST', m['created_at'][11:19], m['content'][max(0,mm.start()-50):mm.end()+30].replace('\n',' '))
