import sys, re
sys.path.insert(0, '/home/claude/review')
from load import rows, ts, T, agents
V='swarm-village'
msgs = sorted(rows(V,'chat_messages'), key=lambda m: ts(m['created_at']))
for m in msgs:
    if m['speaker_type']!='agent':
        c=m['content']
        print(m['created_at'], len(c), 'user_id_present', m['user_speaker_id'] is not None)
        print('   ', re.sub(r'https?://\S+','<URL>',c[:300]).replace('\n',' | '))
