#!/usr/bin/env python3
"""Bounded native-input combat capture in an already prepared solo practice game.

Requires the champion in Baron pit, unlocked camera centered on Baron, and
practice cooldown/health/mana refresh enabled. Does not change game settings.
Stops if focus leaves the game. Presentation CSVs are the frame measure.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path
import requests
import urllib3

urllib3.disable_warnings()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--seconds', type=int, default=60)
args = parser.parse_args()
if not 5 <= args.seconds <= 90:
    raise SystemExit('Duration must be 5–90 seconds')
args.out.mkdir(parents=True, exist_ok=False)

def api(endpoint):
    return requests.get('https://127.0.0.1:2999/liveclientdata/' + endpoint,
                        verify=False, timeout=3).json()

def state():
    player = api('activeplayer')
    return dict(monotonic_ns=time.monotonic_ns(), game=api('gamestats'),
                level=player.get('level'), stats=player.get('championStats'))

if api('gamestats').get('gameMode') != 'PRACTICETOOL' or len(api('playerlist')) != 1:
    raise SystemExit('This automation requires a solo practice match')
windows = subprocess.check_output(['xdotool', 'search', '--class', '^LeagueofLegends$'], text=True).split()
if len(windows) != 1:
    raise SystemExit('Expected exactly one game window')
window = windows[0]
def input_command(*values):
    subprocess.run(['xdotool', *values], check=True, stdout=subprocess.DEVNULL)

before = state()
cycles = 0
reason = 'duration'
deadline = time.monotonic() + args.seconds
while time.monotonic() < deadline:
    active = json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j']))
    if active.get('class') != 'LeagueofLegends':
        reason = 'focus changed'; break
    input_command('mousemove', '--window', window, '1240', '330')
    input_command('click', '--window', window, '3')
    input_command('key', 'q', 'w', 'e', 'r')
    x, y = ((950, 590) if cycles % 2 else (1110, 620))
    input_command('mousemove', '--window', window, str(x), str(y))
    input_command('click', '--window', window, '3')
    time.sleep(.15)
    cycles += 1
after = state()
result = dict(before=before, after=after, cycles=cycles, stop_reason=reason,
              workload='Kindred level 18, no items, Baron pit, repeated Q/W/E/R, movement and attacks; practice refresh enabled')
(args.out / 'window.json').write_text(json.dumps(result, indent=2) + '\n')
wall = (after['monotonic_ns'] - before['monotonic_ns']) / 1e9
clock = after['game']['gameTime'] - before['game']['gameTime']
print(json.dumps(dict(wall_s=wall, active_clock_s=clock, cycles=cycles, stop_reason=reason)))
if reason != 'duration' or not .8 * wall <= clock <= 1.2 * wall:
    raise SystemExit('Reject: focus changed or match clock did not advance normally')
