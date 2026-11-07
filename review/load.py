import gzip, json, datetime, os

BASE = '/home/claude/data/ai-village'


def rows(village, table):
    with gzip.open(os.path.join(BASE, village, table + '.jsonl.gz'), 'rt') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ts(s):
    """Parse naive UTC timestamp with variable fractional digits."""
    if s is None:
        return None
    s = s.replace('T', ' ').rstrip('Z')
    if '.' in s:
        a, b = s.split('.', 1)
        b = (b + '000000')[:6]
        s = a + '.' + b
    else:
        s = s + '.000000'
    return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S.%f')


def T(hm, day=30):
    h, m = hm.split(':')
    return datetime.datetime(2026, 8, day, int(h), int(m))


def agents(village):
    return {r['id']: r['name'] for r in rows(village, 'agents')}
