#!/usr/bin/env python3
"""Pair syscall trace events and rank sleep callers by elapsed time.

Uses perf's recorded call stacks only; never reads the running game's memory.
Usage: python3 tools/analyze-sleep-callers.py logs/sleep-callers
"""
import argparse
import collections
import json
import re
import subprocess
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('directory', type=Path)
a = p.parse_args()
proc = subprocess.Popen(
    ['perf', 'script', '--ns', '-i', str(a.directory / 'sleep.data')],
    stdout=subprocess.PIPE, text=True)
header = re.compile(r'\s+([\d.]+):\s+raw_syscalls:(sys_enter|sys_exit):\s+NR (\d+)')
pending = None
stack = []
groups = collections.defaultdict(list)
names = {35: 'nanosleep', 230: 'clock_nanosleep', 23: 'select', 270: 'pselect6', 7: 'poll'}
first = last = None
for line in proc.stdout:
    m = header.search(line)
    if m:
        timestamp, event, syscall = float(m[1]), m[2], int(m[3])
        if first is None:
            first = timestamp
        last = timestamp
        if event == 'sys_enter':
            pending = (syscall, timestamp)
            stack = []
        else:
            if pending is not None and pending[0] == syscall:
                groups[(syscall, tuple(stack))].append(timestamp - pending[1])
            pending = None
        continue
    if pending is not None and re.match(r'\s+[0-9a-f]+\s+', line):
        stack.append(line.strip())
if proc.wait():
    raise SystemExit('perf script failed')
wall = (last - first) if first is not None else 0
rows = []
for (syscall, frames), durations in groups.items():
    durations.sort()
    total = sum(durations)
    rows.append(dict(syscall=names.get(syscall, str(syscall)), count=len(durations),
                     elapsed_ms=total * 1000, wall_pct=100 * total / wall if wall else 0,
                     median_us=durations[len(durations) // 2] * 1e6,
                     p95_us=durations[int(len(durations) * .95)] * 1e6,
                     frames=frames))
rows.sort(key=lambda r: r['elapsed_ms'], reverse=True)
out = a.directory / 'sleep-summary.json'
out.write_text(json.dumps(dict(wall_s=wall, callers=rows), indent=2) + '\n')
print('Capture duration: %.3f s' % wall)
for row in rows[:12]:
    print('%s: %d calls, %.2f ms (%.2f%% wall), median %.1f us, p95 %.1f us' %
          (row['syscall'], row['count'], row['elapsed_ms'], row['wall_pct'],
           row['median_us'], row['p95_us']))
    for frame in row['frames'][:9]:
        print('  ' + frame)
print('Saved:', out)
