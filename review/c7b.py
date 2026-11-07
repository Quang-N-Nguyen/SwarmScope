import sys, re, collections, json
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
sess={s['id']:s['agent_id'] for s in rows(V,'computer_use_sessions')}
for r in rows(V,'computer_use_turns'):
    t=ts(r['created_at'])
    if t<T('10:00'): continue
    a=r['agent_action']
    if not isinstance(a,dict) or 'command' not in a: continue
    cmd=a['command'] or ''
    if 'git commit' not in cmd: continue
    adds=re.findall(r'git add\s+([^;&|\n]+)',cmd)
    if not any('.py' in x for x in adds): continue
    name=A.get(sess.get(r['session_id']))
    out=((r['output'] or '')+' || ERR '+(r['error'] or '')).replace('\n',' ')
    print('###',str(t)[11:19],name,'| ADD:',[x.strip()[:80] for x in adds])
    print('    OUT:',re.sub(r'https?://\S+','<URL>',out[-300:]))
