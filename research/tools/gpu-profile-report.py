#!/usr/bin/env python3
"""Report from the Indium GPU profiler (CYCLE_GPU_TIMING_DRAWS=1): where GPU time goes and where the GPU waits.
  gpu-profile-report.py [timing.log draws.log pso.log]   (defaults: ~/.darling/tmp/indium-gpu-*.log)
"""
import collections, os, sys
tmp = os.path.expanduser('~/.darling/tmp')
timing, draws, pso = (sys.argv[1:4] + [None] * 3)[:3]
timing = timing or tmp + '/indium-gpu-timing.log'
draws = draws or tmp + '/indium-gpu-draws.log'
pso = pso or tmp + '/indium-gpu-pso.log'

passes = []   # (start_ns, ms, w, h, draws)
for line in open(timing):
    if not line.startswith('cb'): continue
    for tok in line.split()[1:]:
        wh, d, ms, start = tok.split(':')
        w, h = wh.split('x')
        # The 3x3 marker spans the whole command buffer, not a render pass.
        if (int(w), int(h)) == (3, 3): continue
        passes.append((float(start), float(ms), int(w), int(h), int(d)))
passes.sort()
scene = [i for i, p in enumerate(passes) if p[2] == 1024 and p[3] == 1024]   # exactly one shadow-map pass per frame
# one frame = from one shadow pass start to the next
frames = []
for a, b in zip(scene, scene[1:]):
    window = passes[a:b]
    busy = sum(p[1] for p in window)
    span = (passes[b][0] - passes[a][0]) / 1e6
    # busy time as union of intervals (passes can overlap on the timeline)
    iv = sorted((p[0] / 1e6, p[0] / 1e6 + p[1]) for p in window)
    union = 0.0; cur_s, cur_e = iv[0]
    for s, e in iv[1:]:
        if s > cur_e: union += cur_e - cur_s; cur_s, cur_e = s, e
        else: cur_e = max(cur_e, e)
    union += cur_e - cur_s
    frames.append((span, union, busy, len(window)))
frames = [f for f in frames if 3 < f[0] < 80]
n = len(frames)
if n:
    spans = sorted(f[0] for f in frames)
    print('frames analysed: %d' % n)
    print('  frame period      mean %.2f ms   p50 %.2f   p95 %.2f   p99 %.2f' % (sum(spans) / n, spans[n // 2], spans[int(n * .95)], spans[min(n - 1, int(n * .99))]))
    print('  GPU pass time    mean %.2f ms  (sum of render passes)' % (sum(f[2] for f in frames) / n))
    print('  GPU busy (union) mean %.2f ms  -> %.0f%% of the frame' % (sum(f[1] for f in frames) / n, 100 * sum(f[1] for f in frames) / sum(spans)))
    print('  Outside passes   mean %.2f ms per frame (may include copies, compute, fences, present or waiting)' % (sum(f[0] - f[1] for f in frames) / n))
agg = collections.defaultdict(lambda: [0, 0.0, 0])
for p in passes:
    a = agg['%dx%d' % (p[2], p[3])]; a[0] += 1; a[1] += p[1]; a[2] += p[4]
print('\nGPU time by render target (per frame):')
for k, (c, ms, d) in sorted(agg.items(), key=lambda x: -x[1][1])[:8]:
    print('  %-10s %5.1f passes %7.1f draws %6.2f ms' % (k, c / max(len(scene), 1), d / max(len(scene), 1), ms / max(len(scene), 1)))

if os.path.exists(draws):
    names = {}
    for line in open(pso):
        parts = line.split()
        if len(parts) >= 3: names[parts[0]] = (parts[1], parts[2])
    rows = []
    total = 0.0
    for line in open(draws):
        p, wh, c, ms = line.split()
        rows.append((float(ms), int(c), p, wh)); total += float(ms)
    rows.sort(reverse=True)
    frames_n = max(len(scene), 1)
    print('\nGPU time per draw group (pipeline state x target), per frame, total %.2f ms:' % (total / frames_n))
    print('  %6s %6s %7s  %-10s  vertex / fragment function' % ('ms/fr', 'draws', 'us/draw', 'target'))
    for ms, c, p, wh in rows[:30]:
        v, f = names.get(p, ('?', '?'))
        print('  %6.2f %6.1f %7.1f  %-10s  %s / %s' % (ms / frames_n, c / frames_n, 1000 * ms / max(c, 1), wh, v[:42], f[:42]))
