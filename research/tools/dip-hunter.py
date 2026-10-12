#!/usr/bin/env python3
"""Find what causes periodic FPS dips: per second, FPS next to the main thread's wait state and the busiest other processes.
  dip-hunter.py [seconds=40]    (game idle, recorder armed). No root, no ptrace: /proc only."""
import collections, csv, glob, os, sys, time
from pathlib import Path
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 40
def game():
    for e in Path('/proc').iterdir():
        if e.name.isdigit():
            try:
                if (e / 'cmdline').read_bytes().split(b'\0', 1)[0].endswith(b'/Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends'):
                    return int(e.name)
            except OSError: pass
    sys.exit('no game')
pid = game(); tck = os.sysconf('SC_CLK_TCK')
def snapshot():
    out = {}
    for e in os.scandir('/proc'):
        if not e.name.isdigit(): continue
        try:
            st = open('/proc/%s/stat' % e.name).read()
            comm = st[st.index('(') + 1:st.rindex(')')]
            f = st[st.rindex(')') + 2:].split()
            out[int(e.name)] = (comm, int(f[11]) + int(f[12]))
        except (OSError, ValueError, IndexError): pass
    return out
rows = []; prev = snapshot(); t0 = time.monotonic_ns(); end = time.monotonic() + secs
main_states = collections.defaultdict(collections.Counter)
last = time.monotonic()
while time.monotonic() < end:
    time.sleep(0.01)
    try:
        st = open('/proc/%d/stat' % pid).read(); state = st[st.rindex(')') + 2]
        wch = open('/proc/%d/wchan' % pid).read().strip() or '-'
    except OSError: continue
    sec = int((time.monotonic_ns() - t0) / 1e9)
    main_states[sec][state if state == 'R' else 'S:' + wch[:28]] += 1
    now = time.monotonic()
    if now - last >= 1.0:
        cur = snapshot(); sec_i = int((time.monotonic_ns() - t0) / 1e9) - 1
        deltas = []
        for p, (comm, t) in cur.items():
            if p in prev and t > prev[p][1]: deltas.append(((t - prev[p][1]) * 100.0 / tck, p, comm))
        deltas.sort(reverse=True); rows.append((sec_i, deltas[:4])); prev = cur; last = now
abs0 = t0
stamps = set()
deadline = time.monotonic() + 80
while time.monotonic() < deadline:
    stamps.clear()
    for p in glob.glob(os.path.expanduser('~/.darling/tmp/metal-present-intervals*.csv')):
        for r in csv.DictReader(open(p)):
            t = int(r['queued_ns'])
            if abs0 <= t <= abs0 + secs * 1_000_000_000: stamps.add(t)
    if stamps and max(stamps) >= abs0 + (secs - 2) * 1_000_000_000: break
    time.sleep(3)
print('%3s %4s  %-34s  %s' % ('sec', 'fps', 'main thread (most common state)', 'busiest processes (cpu%)'))
for sec, deltas in rows:
    n = sum(1 for t in stamps if abs0 + sec * 1e9 <= t < abs0 + (sec + 1) * 1e9)
    ms = main_states.get(sec, {})
    top = ', '.join('%s %.0f' % (c, d) for d, p, c in deltas if c not in ('perf',))[:80]
    stt = ', '.join('%s %d%%' % (k, 100 * v // max(sum(ms.values()), 1)) for k, v in ms.most_common(2))
    flag = '  <==' if n < 95 else ''
    print('%3d %4d  %-34s  %s%s' % (sec, n, stt[:34], top, flag))
