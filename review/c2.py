import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents

V = 'swarm-village'
A = agents(V)
goals = list(rows(V, 'agent_goals'))
role = {}
for g in goals:
    if g['start_time'] == '2026-08-30 10:00:00':
        m = re.search(r'assigned the role "([^"]+)"', g['description'])
        role[A[g['agent_id']]] = (g['name'], m.group(1) if m else None)
gods = [n for n, (nm, r) in role.items() if r and re.match(r'god\b', r.strip(), re.I) or re.search(r':\s*god\b', nm, re.I)]
print('god-like roles', [(n, role[n]) for n in gods])
print('coral-delta', role['coral-delta'])
print('green-epsilon', role['green-epsilon'])
print('distinct roles', len(set(r for _, r in role.values())))
print('roles containing god', [(n, r) for n, (_, r) in role.items() if r and 'god' in r.lower()])

msgs = sorted(rows(V, 'chat_messages'), key=lambda m: ts(m['created_at']))
cdid = [k for k, v in A.items() if v == 'coral-delta'][0]
for m in msgs:
    if m['agent_speaker_id'] == cdid and re.search(r'\bgod\b', m['content'], re.I) and ts(m['created_at']) > T('10:00'):
        print(m['created_at'], m['content'][:110].replace('\n', ' '))
        break
# earliest message anywhere that says coral-delta claims god
for m in msgs:
    if re.search(r'coral-delta claims god', m['content'], re.I):
        print('phrase first', m['created_at'], A.get(m['agent_speaker_id']))
        break
