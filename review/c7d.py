import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
sess={s['id']:s['agent_id'] for s in rows(V,'computer_use_sessions')}
n=0
for r in rows(V,'computer_use_turns'):
    out=r['output'] or ''
    name=A.get(sess.get(r['session_id']))
    for k in ['1ad0a7f','3260b6e9','b9a7cf3a']:
        i=out.find(k)
        if i>=0 and name not in ('green-epsilon','coral-theta','blue-theta'):
            cmd=(r['agent_action'] or {}).get('command','') or ''
            print(r['created_at'][11:19],name,k,'| CMD has:',[w for w in ['git log','git pull','git show','git fetch'] if w in cmd],'| ...',out[max(0,i-80):i+90].replace('\n',' / '))
