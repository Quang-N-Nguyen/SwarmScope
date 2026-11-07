import sys, re, collections, json
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
sess={s['id']:s['agent_id'] for s in rows(V,'computer_use_sessions')}
role={g['agent_id']:re.search(r'assigned the role "([^"]+)"',g['description']).group(1) for g in rows(V,'agent_goals') if g['start_time']=='2026-08-30 10:00:00'}
push_ok=re.compile(r'\b[0-9a-f]{7,}\.\.[0-9a-f]{7,}\s+\S+\s*->\s*\S+')
commit_ok=re.compile(r'\[(?:main|master|[\w/.-]+)(?: \(root-commit\))? [0-9a-f]{7,}\]')
res=collections.defaultdict(lambda: collections.Counter())
gitcmd=collections.Counter(); ge_cmds=[]
for r in rows(V,'computer_use_turns'):
    t=ts(r['created_at'])
    if t<T('10:00'): continue
    a=r['agent_action']
    if not isinstance(a,dict) or 'command' not in a: continue
    cmd=a['command'] or ''
    aid=sess.get(r['session_id']); name=A.get(aid,'?')
    if name=='green-epsilon' and 'git' in cmd: ge_cmds.append((str(t)[11:19],cmd[:150].replace('\n',' '), str(r['output'])[:120].replace('\n',' ')))
    if 'git commit' not in cmd: continue
    gitcmd[name]+=1
    out=(r['output'] or '')+'\n'+(r['error'] or '')
    adds=re.findall(r'git add\s+([^;&|]+)',cmd)
    stages_py=any('.py' in x for x in adds)
    stages_all=any(re.search(r'(^|\s)(-A|--all|\.)(\s|$)',x) for x in adds) or re.search(r'git commit[^;&|]*\s-[a-zA-Z]*a',cmd)
    landed_push=bool(push_ok.search(out)); landed_commit=bool(commit_ok.search(out))
    k=res[name]
    k['commit_cmd']+=1
    if stages_py: k['py']+=1
    if stages_py and (landed_push or landed_commit): k['py_landed_any']+=1
    if stages_py and landed_push: k['py_landed_push']+=1
    if stages_py and landed_commit: k['py_landed_commit']+=1
    if (stages_py or stages_all) and (landed_push or landed_commit): k['py_or_all_landed']+=1
    if landed_push or landed_commit: k['any_landed']+=1
print('agents running git commit after 10:00:',len(res))
for n,k in sorted(res.items(),key=lambda kv:-kv[1]['any_landed']):
    if k['any_landed'] or k['py']:
        print(n, role[[i for i,v in A.items() if v==n][0]][:28], dict(k))
print('green-epsilon git cmds after 10:00:',len(ge_cmds))
for x in ge_cmds[:15]: print('  ',x)
