import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
msgs = sorted(rows(V,'chat_messages'), key=lambda m: ts(m['created_at']))
ag=[m for m in msgs if m['speaker_type']=='agent']
W={'before':(T('10:17'),T('12:50')),'after':(T('12:50'),T('15:23'))}
# exact op time
op=ts('2026-08-30 12:50:51.076221')
W2={'before(to op msg)':(op-(T('15:23')-T('12:50')),op),'after(op msg+2h33)':(op,op+(T('15:23')-T('12:50')))}
pats={
 'narrow': r'new role|reassign|my role|role (?:changed|shuffled|change|shuffle)|roles? (?:were |was |have been |got )?(?:re)?shuffled',
 'narrow2': r'new role|reassign|my role|role[ -]?(?:changed|shuffled|change|shuffle|swap)',
 'narrow_nomyrole': r'new role|reassign|role[ -]?(?:changed|shuffled|change|shuffle)',
 'any role': r'\broles?\b',
 'any role substring': r'role',
}
for WW in (W,W2):
  for k,(a,b) in WW.items():
    sub=[m for m in ag if a<=ts(m['created_at'])<b]
    out=[k, len(sub)]
    for pn,p in pats.items():
        n=sum(1 for m in sub if re.search(p,m['content'],re.I))
        out.append(f'{pn}={n} ({100*n/len(sub):.1f}%)')
    print(*out)
# show narrow matches after
a,b=W['after']
for m in ag:
    if a<=ts(m['created_at'])<b and re.search(pats['narrow2'],m['content'],re.I):
        mm=re.search(pats['narrow2'],m['content'],re.I)
        print('AFTER', m['created_at'], m['content'][max(0,mm.start()-60):mm.end()+40].replace('\n',' '))
