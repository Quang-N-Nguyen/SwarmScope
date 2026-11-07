import sys, re, collections
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents

V = 'swarm-village'
A = agents(V)
msgs = sorted(rows(V, 'chat_messages'), key=lambda m: ts(m['created_at']))
claim_t = ts('2026-08-30 11:08:23.455636')

def count(target, start, end=None, godre=r'god', flags=re.I, at_ci=False):
    s = set()
    for m in msgs:
        t = ts(m['created_at'])
        if m['speaker_type'] != 'agent' or t < start or (end and t >= end):
            continue
        sp = A.get(m['agent_speaker_id'])
        if sp == target:
            continue
        c = m['content']
        has_at = ('@' + target).lower() in c.lower() if at_ci else ('@' + target) in c
        if has_at and re.search(godre, c, flags):
            s.add(sp)
    return s

for tgt in ['coral-delta', 'green-epsilon']:
    print(tgt)
    print('  after claim, substring god ci:', len(count(tgt, claim_t)))
    print('  after claim, \\bgod\\b ci     :', len(count(tgt, claim_t, godre=r'\bgod\b')))
    print('  after claim, @ ci, god ci   :', len(count(tgt, claim_t, at_ci=True)))
    print('  after 10:00, substring god  :', len(count(tgt, T('10:00'))))
    print('  whole log, substring god    :', len(count(tgt, T('00:00', 29))))
    print('  after claim, before 12:50   :', len(count(tgt, claim_t, T('12:50'))))
# how many distinct agents sent any message after claim (denominator)
print('agents speaking after claim', len({A.get(m['agent_speaker_id']) for m in msgs if m['speaker_type']=='agent' and ts(m['created_at'])>=claim_t}))
both = count('coral-delta', claim_t) & count('green-epsilon', claim_t)
print('overlap', len(both))
