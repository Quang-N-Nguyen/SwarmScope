import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
sess={s['id']:s['agent_id'] for s in rows(V,'computer_use_sessions')}
for r in rows(V,'computer_use_turns'):
    out=r['output'] or ''; name=A.get(sess.get(r['session_id']))
    for k,who in [('3260b6e9','coral-theta'),('b9a7cf3a','blue-theta'),('4cb0679a','coral-delta'),('3446d359','coral-alpha')]:
        i=out.find(k)
        if i>=0:
            cmd=((r['agent_action'] or {}).get('command','') or '')
            print(r['created_at'][11:19],name,k,'| cmd:',cmd[:90].replace('\n',' '),'| out:',out[max(0,i-60):i+70].replace('\n',' / '))
