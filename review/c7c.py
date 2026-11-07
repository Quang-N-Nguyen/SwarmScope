import sys, re, collections, json
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'; A=agents(V)
sess={s['id']:s['agent_id'] for s in rows(V,'computer_use_sessions')}
keys=['1ad0a7f','god patch','65fa57f8','registrar landing','4cb0679a','b9a7cf3a','dotted aliases','3260b6e9','stationer v1.2','tax_ledger','f0ea180f','2dd65794']
hits=collections.defaultdict(list)
amb=[]; coa=[]
for r in rows(V,'computer_use_turns'):
    t=ts(r['created_at'])
    if t<T('10:00'): continue
    out=(r['output'] or '')
    name=A.get(sess.get(r['session_id']))
    for k in keys:
        if k in out: hits[k].append((str(t)[11:19],name))
    a=r['agent_action']; cmd=a.get('command','') if isinstance(a,dict) else ''
    cmd=cmd or ''
    if name=='amber-beta' and T('12:16')<=t<=T('13:30') and 'git' in cmd: amb.append((str(t)[11:19],cmd[:120].replace('\n',' '),out[-200:].replace('\n',' ')))
    if name=='coral-alpha' and T('14:05')<=t<=T('15:30') and 'git' in cmd: coa.append((str(t)[11:19],cmd[:120].replace('\n',' '),out[-200:].replace('\n',' ')))
for k in keys: print(k, len(hits[k]), hits[k][:6])
print('amber-beta follow-ups'); [print('  ',x) for x in amb[:8]]
print('coral-alpha follow-ups'); [print('  ',x) for x in coa[:8]]
