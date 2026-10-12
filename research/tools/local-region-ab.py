#!/usr/bin/env python3
"""Same-match region-query A/B. Requires the diagnostic Baron practice setup.

Uses /tmp/rclol-no-local-region on the HOST, refreshed every 1024 calls.
Keeps graphics settings unchanged. Saves full workload results and CPU samples.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
FLAG = Path('/tmp/rclol-no-local-region')
OUT = ROOT / 'logs/local-region-20261010/free-camera'
env = os.environ.copy()
env.pop('ELECTRON_RUN_AS_NODE', None)

def pid_for(executable):
    for p in Path('/proc').glob('[0-9]*'):
        try:
            first = (p / 'cmdline').read_bytes().split(b'\0')[0].decode()
            if first.endswith(executable):
                return int(p.name)
        except (OSError, UnicodeError):
            pass
    raise RuntimeError(f'process missing: {executable}')

def ticks(pid, main=False):
    fields = Path(f'/proc/{pid}/task/{pid}/stat' if main else f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return int(fields[11]), int(fields[12])

def sample(game, server, result):
    start = time.monotonic()
    a, sa = ticks(game, True), ticks(server)
    time.sleep(15)
    b, sb = ticks(game, True), ticks(server)
    scale = 100 / ((time.monotonic() - start) * os.sysconf('SC_CLK_TCK'))
    result.update(main_user_pct=(b[0]-a[0])*scale, main_sys_pct=(b[1]-a[1])*scale,
                  server_pct=(sum(sb)-sum(sa))*scale)

OUT.mkdir(parents=True, exist_ok=True)
game = pid_for('/Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends')
server = int(subprocess.check_output(['pgrep', '-x', 'darlingserver']).split()[0])
original = FLAG.read_bytes() if FLAG.exists() else None
try:
    for index, mode in enumerate(('off', 'on', 'on', 'off', 'on')):
        if mode == 'off': FLAG.touch()
        else: FLAG.unlink(missing_ok=True)
        time.sleep(3)
        subprocess.run(['darling', 'shell', 'touch', '/tmp/metal-frame-interval-repeat'],
                       env=env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))'],
                       check=True, stdout=subprocess.DEVNULL)
        time.sleep(1)
        cpu = {}
        thread = threading.Thread(target=sample, args=(game, server, cpu))
        thread.start()
        run = subprocess.run([sys.executable, '-I', 'tools/baron-workload.py', '--seconds', '18', '--stationary'],
                             cwd=ROOT, capture_output=True, text=True, timeout=120)
        thread.join()
        (OUT / f'{index}-{mode}-raw.txt').write_text(run.stdout + '\n' + run.stderr)
        if run.returncode: raise RuntimeError(run.stdout + run.stderr)
        data = json.loads(run.stdout[run.stdout.index('{'):])
        data.update(mode=mode, **cpu)
        (OUT / f'{index}-{mode}.json').write_text(json.dumps(data, indent=2) + '\n')
        print(json.dumps(data), flush=True)
        if data['baron_hp_bar_px_end'] is None:
            raise RuntimeError('target lost: reject this comparison')
finally:
    subprocess.run(['xdotool', 'keyup', 'q', 'd'])
    if original is None: FLAG.unlink(missing_ok=True)
    else: FLAG.write_bytes(original)
