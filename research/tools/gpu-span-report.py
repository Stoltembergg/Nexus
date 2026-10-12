#!/usr/bin/env python3
"""Split GPU time per frame into render passes, other work inside command buffers and idle gaps (needs spans: 3x3 entries).
  gpu-span-report.py [timing.log] [first_line] [last_line]     (1-based line range of the log; default all)
"""
import bisect, os, sys
log = (sys.argv[1:2] or [os.path.expanduser('~/.darling/tmp/indium-gpu-timing.log')])[0]
lo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
hi = int(sys.argv[3]) if len(sys.argv) > 3 else 10**12
spans, passes = [], []
for i, line in enumerate(open(log), 1):
    if i < lo or i > hi or not line.startswith('cb'): continue
    for tok in line.split()[1:]:
        wh, d, ms, st = tok.split(':'); w, h = map(int, wh.split('x'))
        st = float(st) / 1e6; ms = float(ms)
        (spans if (w, h) == (3, 3) else passes).append((st, st + ms, w, h, int(d)))
spans.sort(); passes.sort()
shadow = [p[0] for p in passes if (p[2], p[3]) == (1024, 1024)]
def union(iv):
    iv = sorted(iv); t = 0.0
    if not iv: return 0.0
    cs, ce = iv[0]
    for s, e in iv[1:]:
        if s > ce: t += ce - cs; cs, ce = s, e
        else: ce = max(ce, e)
    return t + ce - cs
rows = []
for a, b in zip(shadow, shadow[1:]):
    period = b - a
    if not 3 < period < 120: continue
    sp = [(s, e) for s, e, *_ in spans[bisect.bisect_left(spans, (a,)):bisect.bisect_left(spans, (b,))]]
    ps = [(s, e) for s, e, *_ in passes[bisect.bisect_left(passes, (a,)):bisect.bisect_left(passes, (b,))]]
    su, pu = union(sp), union(ps)
    rows.append((period, su, pu, sum(e - s for s, e in ps), len(sp)))
n = len(rows)
if not n: sys.exit('no frames (does the log contain 3x3 spans?)')
rows.sort()
def show(name, r):
    m = len(r)
    if not m: return
    f = lambda i: sum(x[i] for x in r) / m
    print('%-14s n=%5d period %6.2f | cmdbuf spans %5.2f (%d/frame) | render passes %5.2f | non-render in cmdbufs %5.2f | gaps (idle) %5.2f' %
          (name, m, f(0), f(1), round(f(4)), f(2), f(1) - f(2), f(0) - f(1)))
show('all', rows)
show('fast half', rows[:n // 2])
show('slow half', rows[n // 2:])
show('slowest 5%', rows[int(n * .95):])
