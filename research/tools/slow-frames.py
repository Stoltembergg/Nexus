#!/usr/bin/env python3
"""Split a tools/true-profile.sh capture into frames and compare slow frames with typical ones.

  slow-frames.py <capture-dir> [marker-substring]
A frame boundary is a main-thread switch-out whose stack contains the marker (default: the once-per-frame semaphore wait
below game function 0x101996930). For each frame: duration, off-CPU time, and on-CPU samples bucketed by where they are.
"""
import collections, statistics, sys
from pathlib import Path
src = (Path(__file__).resolve().parent / 'analyze-profile.py').read_text()
cap_dir = sys.argv[1]; marker = sys.argv[2] if len(sys.argv) > 2 else '0x101996930'
ns = {'__file__': str(Path(__file__).resolve().parent / 'analyze-profile.py')}
sys.argv = ['x', cap_dir, 'offcpu']
exec(src[:src.index("if mode == 'oncpu':")], ns)
events, label_frames, is_kernel, game = ns['events'], ns['label_frames'], ns['is_kernel'], ns['game']
import re
bounds = []; off = []; pending = None
for tid, t, ev, rest, frames in events():
    if ev != 'sched:sched_switch': continue
    m = re.search(r'prev_pid=(\d+).*?next_pid=(\d+)', rest)
    if not m: continue
    if int(m[1]) == game:
        names = label_frames(frames)
        if any(marker in n for n, d in names): bounds.append(t)
        pending = (t, names)
    if int(m[2]) == game and pending:
        off.append((pending[0], t - pending[0], pending[1])); pending = None
ns['mode'] = 'oncpu'
BUCKETS = [('event pump', ('nextEventMatchingMask',)), ('metal commit/present', ('commit]', 'present', 'PrivateCommandBuffer::commit')),
           ('texture upload', ('replaceRegion',)), ('indium encode', ('Indium::',)), ('metal bridge', ('[MTL', 'Metal')), ('objc', ('objc_',))]
def bucket(names, frames):
    text = ' '.join(n for n, d in names)
    for label, keys in BUCKETS:
        if any(k in text for k in keys): return label
    return 'game code' if not is_kernel(frames[0][2]) else 'game code -> kernel'
samples = []
for tid, t, ev, rest, frames in events():
    if tid == game and frames:
        nm = label_frames(frames)
        samples.append((t, bucket(nm, frames), nm))
fr = []
import bisect
st = [s[0] for s in samples]; ot = [o[0] for o in off]
for a, b in zip(bounds, bounds[1:]):
    c = collections.Counter(s[1] for s in samples[bisect.bisect_left(st, a):bisect.bisect_left(st, b)])
    o = sum(x[1] for x in off[bisect.bisect_left(ot, a):bisect.bisect_left(ot, b)])
    fr.append((b - a, o, c, samples[bisect.bisect_left(st, a):bisect.bisect_left(st, b)], off[bisect.bisect_left(ot, a):bisect.bisect_left(ot, b)]))
d = sorted(f[0] for f in fr)
print('frames %d  mean %.1f ms  median %.1f  p95 %.1f  p99 %.1f  max %.1f' % (len(d), 1e3*statistics.mean(d), 1e3*d[len(d)//2], 1e3*d[int(len(d)*.95)], 1e3*d[int(len(d)*.99)], 1e3*d[-1]))
def show(label, sel):
    n = len(sel); tot = collections.Counter()
    for f in sel: tot.update(f[2])
    print('\n%s: %d frames, mean %.1f ms, off-CPU %.1f ms' % (label, n, 1e3*sum(f[0] for f in sel)/n, 1e3*sum(f[1] for f in sel)/n))
    for k, v in tot.most_common(): print('   %5.2f ms  %s' % (v/0.999/n, k))
lo, hi = d[int(len(d)*.25)], d[int(len(d)*.75)]
show('typical frames (25th-75th percentile)', [f for f in fr if lo <= f[0] <= hi])
show('slowest 5%', [f for f in fr if f[0] >= d[int(len(d)*.95)]])

slow = [f for f in fr if f[0] >= d[int(len(d)*.95)]]
inc = collections.Counter(); n = 0
for f in slow:
    for t, b, nm in f[3]:
        if b != 'event pump': continue
        n += 1
        names = [x for x, _ in nm]
        i = max(k for k, x in enumerate(names) if 'nextEventMatchingMask' in x)
        for x in set(names[:i]): inc[x] += 1
print('\nevent pump in slow frames: inclusive callees (%d samples)' % n)
for k, v in inc.most_common(40): print('  %5.1f%%  %s' % (100*v/n, k[:120]))
oc = collections.Counter(); on = collections.Counter()
for f in slow:
    for t0, dur, nm in f[4]:
        names = [x for x, _ in nm]
        key = next((x for x in names if x.startswith('-[') or 'CFRunLoop' in x or 'X11' in x or x.startswith('X')), names[-1] if names else '?')
        oc[key] += dur; on[key] += 1
print('\noff-CPU in slow frames by first ObjC/CF/X frame (ms per slow frame, waits per frame)')
for k, v in oc.most_common(14): print('  %6.2f ms %6.1f  %s' % (1e3*v/len(slow), on[k]/len(slow), k[:110]))
