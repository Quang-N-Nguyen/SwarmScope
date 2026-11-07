import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
msgs=sorted(rows(V,'chat_messages'),key=lambda m: ts(m['created_at']))
ag=[m for m in msgs if m['speaker_type']=='agent']
for pat,flags in [('OWNERS.md',0),('owners.md',re.I),(r'OWNERS\b',0)]:
    s={A[m['agent_speaker_id']] for m in ag if re.search(re.escape(pat) if pat.endswith('.md') else pat, m['content'], flags)}
    print(pat,'flags',flags,'agents',len(s))
first=[m for m in msgs if 'OWNERS.md' in m['content']][0]; print('OWNERS.md first',first['created_at'])
hm=[m for m in ag if 'a484c70d' in m['content']]
t0=ts(hm[0]['created_at']); print('a484c70d first',hm[0]['created_at'],A[hm[0]['agent_speaker_id']],'msgs',len(hm),'agents total',len({m['agent_speaker_id'] for m in hm}))
for mins in (10,14,15,20,30,60):
    s={m['agent_speaker_id'] for m in hm if (ts(m['created_at'])-t0).total_seconds()<=mins*60}
    print(' within',mins,'min:',len(s))
# also 7-char form a484c70
print('a484c70 any', len({m['agent_speaker_id'] for m in ag if 'a484c70' in m['content']}))
# what does the hash relate to (short)
c=hm[0]['content']; i=c.find('a484c70d'); print(repr(c[max(0,i-80):i+60]))
fa={}
for m in hm: fa.setdefault(m['agent_speaker_id'],ts(m['created_at']))
v=sorted(fa.values()); print('40th agent at',v[-1],'span min',(v[-1]-t0).total_seconds()/60, 'last msg',hm[-1]['created_at'])
# mentions in computer_use? skip. Check if any appear in other rooms/time cluster
import collections
print(collections.Counter(str(x)[11:15] for x in v))
