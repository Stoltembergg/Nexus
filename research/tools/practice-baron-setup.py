#!/usr/bin/env python3
"""Prepare a running Practice Tool match for the Baron fight benchmark: level 18, then fast-forward to Baron.

  practice-baron-setup.py [--toggles]
The practice tool panel (left edge of the game window) has no state feedback, so --toggles clicks, once, the buttons that
make the fast-forward survivable: Toggle Minion Spawn (waves stop; otherwise they destroy the nexus while time is skipped),
Toggle Towers Invincible. Use it once per match; running it twice undoes it. Button positions (hover tooltips, 1080p):
  y=535 Kill Player Champion   570 Toggle Towers Invincible   606 Toggle Tower Fire   641 Toggle Minion Spawn
  677 Fast Forward 30sec       712 Fast Forward 10min          747 Reset Game          783 Win The Game
After every 10 minute step the live event list is checked and the script stops if the game ended or a structure fell.
The compositor cursor is moved with hyprctl so the game sees real hover/click input.
"""
import json, subprocess, sys, time
import requests, urllib3
urllib3.disable_warnings()
API = 'https://127.0.0.1:2999/liveclientdata/'

def get(path):
    return requests.get(API + path, verify=False, timeout=3).json()

def focus():
    subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))'], check=True, stdout=subprocess.DEVNULL)
    time.sleep(.5)
    active = json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j']))
    if active.get('class') != 'LeagueofLegends':
        sys.exit('game window is not focused')
    return json.loads(subprocess.check_output(['hyprctl', 'monitors', '-j']))

WINDOW = subprocess.check_output(['xdotool', 'search', '--class', '^LeagueofLegends$'], text=True).split()[0]

def click(x, y, count=1, delay=.12):
    # window-relative XTEST click: the form that the game's panel accepted in the earlier setup runs
    subprocess.run(['xdotool', 'mousemove', '--window', WINDOW, str(x), str(y), 'click', '--window', WINDOW,
                    '--repeat', str(count), '--delay', str(int(delay * 1000)), '1'], check=True)

def losses():
    bad = []
    for e in get('eventdata')['Events']:
        if e['EventName'] in ('GameEnd', 'InhibKilled', 'InhibRespawningSoon') or (e['EventName'] == 'TurretKilled' and 'Order' in e.get('TurretKilled', '')):
            bad.append(e['EventName'] + ' ' + str(e.get('EventTime')))
    return bad

focus()
if get('gamestats')['gameMode'] != 'PRACTICETOOL':
    sys.exit('not a practice tool match')
if '--toggles' in sys.argv:
    click(30, 641); click(30, 570)
if get('activeplayer')['level'] < 18:
    click(30, 373, 17)
    for x, n in [(827, 5), (870, 5), (914, 5), (957, 3)]:
        click(x, 974, n)
time.sleep(1)
print('level', get('activeplayer')['level'], 'clock', round(get('gamestats')['gameTime']))
while get('gamestats')['gameTime'] < 1215:
    click(30, 712)
    last = get('gamestats')['gameTime']
    for _ in range(40):
        time.sleep(1.5)
        now = get('gamestats')['gameTime']
        if now - last < 4 and now > last:  # the fast forward has settled
            break
        last = now
    print('clock', round(now), flush=True)
    bad = losses()
    if bad:
        sys.exit('match state damaged: ' + ', '.join(bad))
print('ready: clock', round(get('gamestats')['gameTime']))
