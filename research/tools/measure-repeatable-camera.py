#!/usr/bin/env python3
"""Automate a bounded practice camera test using X11 input/paint events.

No root, debugger or game memory access. Requires an existing practice match.
The test recenters the camera and pans the same rectangle repeatedly. This
measures camera movement; it does not certify combat or compositor scanout FPS.
"""
import argparse
import csv
import json
import math
import re
import statistics
import subprocess
import time
from pathlib import Path
import requests
import urllib3

urllib3.disable_warnings()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--seconds', type=int, default=30)
parser.add_argument('--min-clock', type=float, default=90, help='Minimum active match time before measurement')
args = parser.parse_args()
if not 5 <= args.seconds <= 600:
    raise SystemExit('Duration must be 5–600 seconds')
args.out.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parent.parent


def command(*values):
    subprocess.run(values, check=True, stdout=subprocess.DEVNULL)


def clock():
    try:
        return requests.get('https://127.0.0.1:2999/liveclientdata/gamestats',
                            verify=False, timeout=2).json().get('gameTime')
    except (requests.RequestException, ValueError):
        return None


deadline = time.monotonic() + 240
window = None
while time.monotonic() < deadline:
    tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
    match = re.search(r'(0x[0-9a-f]+) "League of Legends \(TM\) Client".*?1920x1080', tree)
    if match and clock() is not None:
        window = match[1]
        break
    time.sleep(2)
if not window:
    raise SystemExit('No live 1080p game window')

# The idle UI helpers can be stopped while their last window still covers the
# game. Hide that specific window for the test; the full runtime cycle restores
# the client, and no fullscreen mode or compositor setting is changed.
hidden = re.findall(r'(0x[0-9a-f]+).*?\("LeagueClientUx" "LeagueClientUx"\)', tree)
for ui in hidden:
    command('xdotool', 'windowunmap', ui)
command('xdotool', 'windowactivate', window)
time.sleep(1)
c0 = clock()
time.sleep(1)
c1 = clock()
if c0 is not None and c1 is not None and c1 - c0 < .5:
    # Local practice control; no chat content or messages to other people.
    command('xdotool', 'key', '--window', window, 'Return')
    time.sleep(.3)  # Wait until the game has opened chat before typing the slash.
    command('xdotool', 'type', '--window', window, '--clearmodifiers', '--delay', '60', '/resume')
    time.sleep(.2)
    command('xdotool', 'key', '--window', window, 'Return')
    time.sleep(3)
    c0 = clock()
    time.sleep(2)
    c1 = clock()
    if c0 is None or c1 is None or c1 - c0 < 1:
        raise SystemExit('Practice clock did not resume; no measurement accepted')

warm_deadline = time.monotonic() + max(120, args.min_clock + 30)
while True:
    current_clock = clock()
    if current_clock is not None and current_clock >= args.min_clock:
        break
    if time.monotonic() >= warm_deadline:
        raise SystemExit('Warmup clock did not reach the requested time')
    time.sleep(2)
command('xdotool', 'key', '--window', window, 'space')
time.sleep(2)
before = {'monotonic_s': time.monotonic(), 'game_clock': clock()}
csv_path = args.out / 'window-updates.csv'
observer = subprocess.Popen([str(root / 'build/measure-game-window-updates'), window,
                             str(args.seconds), str(csv_path)], stdout=subprocess.PIPE, text=True)
print('Automated camera test started', flush=True)
pressed = None
try:
    while observer.poll() is None:
        for key in ('Right', 'Down', 'Left', 'Up'):
            if observer.poll() is not None:
                break
            pressed = key
            command('xdotool', 'keydown', '--window', window, key)
            time.sleep(.7)
            command('xdotool', 'keyup', '--window', window, key)
            pressed = None
        command('xdotool', 'key', '--window', window, 'space')
finally:
    if pressed:
        subprocess.run(['xdotool', 'keyup', '--window', window, pressed])
    if observer.poll() is None:
        observer.terminate()
observer_output = observer.communicate()[0]
after = {'monotonic_s': time.monotonic(), 'game_clock': clock()}
rows = list(csv.DictReader(csv_path.open()))
intervals = [(int(b['arrival_ns']) - int(a['arrival_ns'])) / 1e6
             for a, b in zip(rows, rows[1:])]
if observer.returncode or len(intervals) < 10:
    raise SystemExit('Insufficient window updates; no measurement accepted')
wall = after['monotonic_s'] - before['monotonic_s']
active = (before['game_clock'] is not None and after['game_clock'] is not None and
          .8 * wall <= after['game_clock'] - before['game_clock'] <= 1.2 * wall)
ordered = sorted(intervals)
result = dict(before=before, after=after, active_clock=active, update_count=len(rows),
              mean_window_updates_per_s=1000 / statistics.mean(intervals),
              median_ms=statistics.median(intervals), p99_ms=ordered[math.ceil(len(ordered) * .99) - 1],
              target_interval_ms=1000 / 90,
              over_target_pct=100 * sum(x > 1000 / 90 for x in intervals) / len(intervals),
              p99_target_met=ordered[math.ceil(len(ordered) * .99) - 1] < 1000 / 90,
              max_ms=max(intervals), note='X11 paint notifications during automated camera panning. '
              'Validate against FPS HUD; not combat or compositor scanout evidence.')
(args.out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(observer_output.strip())
print(json.dumps(result, indent=2))
if not active:
    raise SystemExit('Clock did not advance normally; reject this capture')
