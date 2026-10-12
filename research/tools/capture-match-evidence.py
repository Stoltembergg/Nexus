#!/usr/bin/env python3
"""Capture live-play CPU samples and the game window; optional costly pass readbacks."""
from pathlib import Path
import os
import re
import subprocess
import time
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
root = Path(__file__).resolve().parent.parent
tag = time.strftime('artifact-%Y%m%d-%H%M%S')
out = root / 'logs' / tag
out.mkdir(exist_ok=True)
deadline = time.monotonic() + 1200
previous_clock = None
previous_sample = None
while time.monotonic() < deadline:
    try:
        response = requests.get('https://127.0.0.1:2999/liveclientdata/gamestats', verify=False, timeout=3)
        clock = response.json().get('gameTime', 0)
        sample = time.monotonic()
        if clock >= 15 and previous_clock is not None and (sample - previous_sample) * 0.8 <= clock - previous_clock <= (sample - previous_sample) * 1.2:
            break
        previous_clock, previous_sample = clock, sample
    except (requests.RequestException, ValueError):
        pass
    time.sleep(5)
else:
    raise SystemExit('Timed out waiting for a running game clock >= 15 s')

print('Steady-play performance capture', out, flush=True)
with (out / 'perf.txt').open('w') as log:
    subprocess.run(['python3', '-I', str(root / 'tools/capture-game-perf.py'), '--seconds', '10', '--out', str(out / 'perf')], cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=60)

# Capture only the named game drawable; never raise it or capture the desktop.
tree = subprocess.run(['xwininfo', '-root', '-tree'], capture_output=True, text=True, timeout=10).stdout
match = re.search(r'(0x[0-9a-f]+) "League of Legends \(TM\) Client"', tree)
if match:
    capture = subprocess.run(['xwd', '-silent', '-id', match[1], '-out', str(out / 'game.xwd')], timeout=10)
    if capture.returncode == 0:
        subprocess.run(['magick', str(out / 'game.xwd'), str(out / 'game.png')], timeout=10)

if os.environ.get('RCLOL_CAPTURE_PASSES') != '1':
    print('Capture complete; render-pass readbacks disabled to avoid callback stalls', flush=True)
    raise SystemExit(0)

print('Capturing up to 30 render-pass outputs (costly diagnostic)', flush=True)
try:
    subprocess.run(['darling', 'shell', 'sh', '-c', f'echo {tag} > /tmp/metal-snapshot'], check=True, timeout=30, stdout=subprocess.DEVNULL)
    time.sleep(5)
finally:
    subprocess.run(['darling', 'shell', 'sh', '-c', 'rm -f /tmp/metal-snapshot'], timeout=30, stdout=subprocess.DEVNULL)
print('Capture complete; render passes are in ~/.darling/tmp/snap-' + tag + '-*.ppm', flush=True)
