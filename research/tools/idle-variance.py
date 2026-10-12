#!/usr/bin/env python3
"""Why does idle FPS wander? Sample CPU/GPU clocks, power and temperature at 4 Hz for N s and line them up with the
frames presented in each second (present-interval CSVs). Run while the game idles (recorder armed, CYCLE_FRAME_INTERVALS=1).
  idle-variance.py [seconds=40]"""
import csv, glob, os, subprocess, sys, time
from pathlib import Path
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 40
dev = Path('/sys/class/drm/card1/device')
def rd(p, default=0.0):
    try: return float(Path(p).read_text().split()[0])
    except (OSError, ValueError, IndexError): return default
def sclk():
    for l in (dev / 'pp_dpm_sclk').read_text().splitlines():
        if l.rstrip().endswith('*'): return int(l.split(':')[1].strip().split('M')[0])
    return 0
hw = next(iter(glob.glob(str(dev / 'hwmon/hwmon*'))), None)
def cpu_freqs():
    f = [rd('/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq' % i) / 1000 for i in range(12)]
    return max(f), f[1]
rows = []
t0 = time.monotonic_ns()
end = time.monotonic() + secs
while time.monotonic() < end:
    mx, c1 = cpu_freqs()
    rows.append(dict(t=(time.monotonic_ns() - t0) / 1e9, abs_ns=time.monotonic_ns(), cpu_max=mx, cpu1=c1, sclk=sclk(),
                     busy=rd(dev / 'gpu_busy_percent'),
                     pw=(rd(hw + '/power1_average') or rd(hw + '/power1_input')) / 1e6 if hw else 0,
                     temp=rd(hw + '/temp1_input') / 1000 if hw else 0))
    time.sleep(0.25)
# frames per second: wait until the block holding the last sample has been flushed
deadline = time.monotonic() + 80
stamps = set()
while time.monotonic() < deadline:
    stamps.clear()
    for p in glob.glob(os.path.expanduser('~/.darling/tmp/metal-present-intervals*.csv')):
        for r in csv.DictReader(open(p)):
            t = int(r['queued_ns'])
            if rows[0]['abs_ns'] <= t <= rows[-1]['abs_ns']: stamps.add(t)
    if stamps and max(stamps) >= rows[-1]['abs_ns'] - 1.5e9: break
    time.sleep(3)
ts = sorted(stamps)
print('%4s %5s %7s %6s %5s %5s %6s %5s' % ('sec', 'fps', 'cpu1', 'cpuMax', 'sclk', 'busy', 'W', 'C'))
for s in range(secs):
    a, b = rows[0]['abs_ns'] + s * 1e9, rows[0]['abs_ns'] + (s + 1) * 1e9
    n = sum(1 for t in ts if a <= t < b)
    w = [r for r in rows if s <= r['t'] < s + 1]
    if not w: continue
    m = lambda k: sum(r[k] for r in w) / len(w)
    print('%4d %5d %7.0f %6.0f %5.0f %4.0f%% %6.1f %5.0f' % (s, n, m('cpu1'), m('cpu_max'), m('sclk'), m('busy'), m('pw'), m('temp')))
