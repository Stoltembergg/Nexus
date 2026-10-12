#!/usr/bin/env python3
"""Summarise an Indium GPU timing log (CYCLE_GPU_TIMING=1): GPU ms per frame by render target size.
  gpu-timing-summary.py <log> [<log2> ...]"""
import collections, sys
for path in sys.argv[1:]:
    agg = collections.defaultdict(lambda: [0, 0.0, 0]); frames = 0
    for line in open(path):
        if not line.startswith('cb'): continue
        for tok in line.split()[1:]:
            wh, d, ms = tok.split(':'); a = agg[wh]; a[0] += 1; a[1] += float(ms); a[2] += int(d)
            if wh == '1920x1080' and int(d) > 100: frames += 0.5
    frames = max(frames, 1)
    print('%s  (%d frames)' % (path, frames))
    total = 0
    for wh, (n, ms, d) in sorted(agg.items(), key=lambda x: -x[1][1]):
        total += ms
        print('  %-12s passes %5.1f  draws %6.1f  GPU %6.2f ms/frame' % (wh, n / frames, d / frames, ms / frames))
    print('  total %.2f ms/frame in render passes' % (total / frames))
