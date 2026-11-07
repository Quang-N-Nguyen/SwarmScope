import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents

V = 'swarm-village'
A = agents(V)
print('agents', len(A), 'unique names', len(set(A.values())))
msgs = list(rows(V, 'chat_messages'))
print('chat msgs', len(msgs), collections.Counter(m['speaker_type'] for m in msgs))
tt = sorted(ts(m['created_at']) for m in msgs)
print('first', tt[0], 'last', tt[-1])

# claim 2: agent_goals
goals = list(rows(V, 'agent_goals'))
print('goals', len(goals))
starts = collections.Counter((g['start_time'], g['end_time']) for g in goals)
print(starts)
created = collections.Counter(g['created_at'][:16] for g in goals)
print('created_at minute buckets', created.most_common(5))
# phase-2 goals: those not ending at 10:00
ph2 = [g for g in goals if g['end_time'] != '2026-08-30 10:00:00']
print('phase2 goals', len(ph2), collections.Counter(g['name'][:40] for g in ph2).most_common(3))
# find a role string in description
ex = ph2[0]['description']
idx = ex.lower().find('role')
print(repr(ex[max(0, idx-200): idx+300]))
