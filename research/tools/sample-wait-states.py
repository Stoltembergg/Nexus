#!/usr/bin/env python3
"""Passive sampler: what is the game's main thread doing, wait-state wise?

Reads /proc/<pid>/task/<tid>/{stat,wchan} (no ptrace, no memory access) at ~2 kHz for N seconds and reports the share of
time spent running, runnable, and blocked per kernel wait function (e.g. waiting on the darlingserver RPC socket, futex,
GPU fence wait). Usage: sample-wait-states.py [seconds=15]
"""
import argparse, collections, csv, sys, time
from pathlib import Path

def game_pid():
    for e in Path('/proc').iterdir():
        if e.name.isdigit():
            try:
                argv0 = (e / 'cmdline').read_bytes().split(b'\0', 1)[0]
            except OSError:
                continue
            if argv0.endswith(b'/LeagueofLegends'):
                return int(e.name)
    sys.exit('no game process')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('seconds', type=float, nargs='?', default=15)
parser.add_argument('--csv', type=Path, help='Optional timestamped diagnostic samples')
args = parser.parse_args()
seconds = args.seconds
if not 0 < seconds <= 60: parser.error('duration must be between zero and 60 seconds')
output = args.csv.open('w') if args.csv else None
writer = csv.writer(output) if output else None
if writer: writer.writerow(['monotonic_ns', 'state'])
pid = game_pid()
stat = open(f'/proc/{pid}/task/{pid}/stat', 'rb', buffering=0)
wchan = open(f'/proc/{pid}/task/{pid}/wchan', 'rb', buffering=0)
counts = collections.Counter()
end = time.monotonic() + seconds
n = 0
while time.monotonic() < end:
    stat.seek(0); s = stat.read()
    state = s[s.rindex(b')') + 2:s.rindex(b')') + 3].decode()
    if state == 'R':
        key = 'running/runnable'
        counts[key] += 1
    else:
        wchan.seek(0)
        key = state + ':' + (wchan.read().decode().strip() or '0')
        counts[key] += 1
    if writer: writer.writerow([time.monotonic_ns(), key])
    n += 1
    time.sleep(0.0004)
if output: output.close()
print(f'pid {pid}: {n} samples in {seconds:.0f}s')
for k, v in counts.most_common(12):
    print('%6.1f%%  %s' % (100 * v / n, k))
