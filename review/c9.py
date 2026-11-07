import sys, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts
for V in ['main-village','open-chat-village']:
    A=list(rows(V,'agents'))
    cm=collections.Counter(m['speaker_type'] for m in rows(V,'chat_messages'))
    vg=list(rows(V,'village_goals'))
    print(V,'agents',len(A),'unique ids',len({a['id'] for a in A}),'unique names',len({a['name'] for a in A}))
    print('  chat',sum(cm.values()),dict(cm))
    print('  village_goals',len(vg),'distinct goal texts',len({g['goal'] for g in vg}))
    st=sorted(ts(g['start_time']) for g in vg if g['start_time'])
    print('  first goal start',st[0] if st else None,'last',st[-1] if st else None)
