#!/usr/bin/env python3
"""A/B the GPU DPM policy (high vs auto) with the real Baron workload; restores the original policy.

  python3 -I tools/baron-gpu-ab.py          (as the normal user, from a terminal: it asks for sudo once)
Why: the game is bound by one CPU thread while the GPU is ~28% busy, and CPU and GPU share one ~20-30 W APU budget; a GPU
pinned at `high` may take watts the CPU core could use as clock. Order high, auto, high, auto so drift cancels.
Prints fps/p99 from the present-interval CSVs plus the CPU1 clock and GPU clock sampled during each run.
"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
root = Path(__file__).resolve().parent.parent
os.chdir(root)
dev = Path('/sys/class/drm/card1/device/power_dpm_force_performance_level')
initial = dev.read_text().strip()
if initial not in ('high', 'auto'):
    sys.exit('unexpected GPU policy ' + initial)
env = os.environ.copy(); env.pop('ELECTRON_RUN_AS_NODE', None)
subprocess.run(['sudo', '-v'], check=True)
subprocess.run(['darling', 'shell', 'sh', '-c', 'touch /tmp/metal-frame-interval-repeat'], env=env, check=True, stdout=subprocess.DEVNULL, timeout=90)
flag = Path.home() / '.darling/tmp/metal-frame-interval-repeat'
t0 = time.monotonic()
while flag.exists() and time.monotonic() - t0 < 400:   # the recorder consumes the flag when it re-arms
    subprocess.run(['sudo', '-n', '-v']); time.sleep(2)

def set_policy(value):
    subprocess.run(['sudo', '-n', 'tee', str(dev)], input=value + '\n', text=True, check=True, stdout=subprocess.DEVNULL)

def sclk():
    for line in Path('/sys/class/drm/card1/device/pp_dpm_sclk').read_text().splitlines():
        if line.rstrip().endswith('*'):
            return int(line.split(':')[1].strip().split('M')[0])
    return 0

results = []
try:
    for label in ['high', 'auto', 'high', 'auto']:
        set_policy(label); time.sleep(4)
        cpu, gpu, stop = [], [], threading.Event()
        def sample():
            while not stop.is_set():
                cpu.append(int(Path('/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq').read_text()) / 1000)
                gpu.append(sclk()); time.sleep(0.2)
        th = threading.Thread(target=sample); th.start()
        out = subprocess.run([sys.executable, '-I', 'tools/baron-workload.py', '--seconds', '30'], capture_output=True, text=True)
        stop.set(); th.join()
        try:
            r = json.loads(out.stdout[out.stdout.index('{'):out.stdout.rindex('}') + 1])
        except ValueError:
            r = {'error': (out.stdout + out.stderr)[-200:]}
        r.update(policy=label, cpu1_mhz=round(sum(cpu) / max(len(cpu), 1)), gpu_mhz=round(sum(gpu) / max(len(gpu), 1)))
        results.append(r); print(json.dumps(r), flush=True)
finally:
    set_policy(initial)
    print('GPU policy restored to', initial)
