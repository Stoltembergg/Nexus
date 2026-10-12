#!/usr/bin/env python3
"""Which render passes cost the GPU? Skip the draws of passes by attachment size (Indium diagnostic flag files) while the
Baron workload runs, and report fps / frame time / GPU busy for each case. No sudo. The picture is wrong while a flag is
set; flags are removed at the end.
"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
root = Path(__file__).resolve().parent.parent
os.chdir(root)
env = os.environ.copy(); env.pop('ELECTRON_RUN_AS_NODE', None)
tmp = Path.home() / '.darling/tmp'
def guest(cmd):
    subprocess.run(['darling', 'shell', 'sh', '-c', cmd], env=env, check=True, stdout=subprocess.DEVNULL, timeout=120)
# The recorder is a bounded capture: only rearm (and wait for it) when it has actually stopped writing blocks.
newest = max((f.stat().st_mtime for f in tmp.glob('metal-present-intervals*.csv')), default=0)
if time.time() - newest > 45:
    guest('rm -f /tmp/metal-skip-*; touch /tmp/metal-frame-interval-repeat')
    t0 = time.monotonic()
    while (tmp / 'metal-frame-interval-repeat').exists() and time.monotonic() - t0 < 400:
        time.sleep(2)
else:
    guest('rm -f /tmp/metal-skip-*')
cases = [('warm-up', None), ('none', None), ('UI pass 1920x1080 linear', 'ui'), ('scene passes 1920x1080', 'scene'), ('none', None), ('UI pass 1920x1080 linear', 'ui'), ('none', None)]
busy_path = Path('/sys/class/drm/card1/device/gpu_busy_percent')
for label, flag in cases:
    guest('rm -f /tmp/metal-skip-*' + (f'; touch /tmp/metal-skip-{flag}' if flag else ''))
    time.sleep(1.5)
    samples, stop = [], threading.Event()
    def sample():
        while not stop.is_set():
            try: samples.append(int(busy_path.read_text()))
            except (OSError, ValueError): pass
            time.sleep(0.1)
    th = threading.Thread(target=sample); th.start()
    out = subprocess.run([sys.executable, '-I', 'tools/baron-workload.py', '--seconds', '18'], capture_output=True, text=True)
    stop.set(); th.join()
    try:
        r = json.loads(out.stdout[out.stdout.index('{'):out.stdout.rindex('}') + 1])
        print('%-22s fps %5.1f  mean %5.1f ms  p50 %5.1f  p99 %5.1f   gpu busy %3.0f%%' % (
            label, r['fps'], r['mean_ms'], r['p50_ms'], r['p99_ms'], sum(samples) / max(len(samples), 1)), flush=True)
    except ValueError:
        print(label, 'no result:', (out.stdout + out.stderr)[-160:], flush=True)
guest('rm -f /tmp/metal-skip-*')
