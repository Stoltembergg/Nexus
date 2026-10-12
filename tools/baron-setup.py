#!/usr/bin/env python3
"""Put a fresh Practice Tool match into the Baron-fight state with real input (see memory: game-fps-true-profile-findings).

  baron-setup.py            level 18 + skills, auto-refresh, towers invincible, minion spawn off, Baron spawned, teleported
                            into the pit, preserving the free camera
Coordinates are for the 1080p panel at the left edge of the game window. Page 1 buttons: 232/266/301 refresh
cooldowns/HP/mana, 372 level up, 443 teleport, 570 towers invincible, 641 toggle minion spawn; arrows y=183 / 877 change
the page; on page 3 button y=302 is Spawn Baron. Needs the game window focused on its monitor (hyprctl).
"""
import json, subprocess, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uinput_click import Mouse, hover
from practice_layout import practice_layout
import requests, urllib3
urllib3.disable_warnings()
API = 'https://127.0.0.1:2999/liveclientdata/'
def get(p): return requests.get(API + p, verify=False, timeout=3).json()

subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))'], check=True, stdout=subprocess.DEVNULL)
time.sleep(.6)
if json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j'])).get('class') != 'LeagueofLegends':
    sys.exit('game window is not focused (is it on the visible workspace?)')
if get('gamestats')['gameMode'] != 'PRACTICETOOL':
    sys.exit('not a practice tool match')
subprocess.run(['xdotool', 'keyup', 'Alt_L', 'Alt_R', 'Control_L', 'Control_R', 'Shift_L', 'Shift_R'])
layout = practice_layout()
m = Mouse()
def click(x, y, n=1):
    if json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j'])).get('class') != 'LeagueofLegends':
        raise SystemExit('game lost focus: stopping practice setup')
    hover(x, y, settle=0.25); m.click(n)
try:
    click(layout["x"], layout["level"], 17)
    time.sleep(.5)
    if get('activeplayer').get('level') != 18:
        raise SystemExit('level-up control did not reach level 18: stopping before further panel clicks')
    for x, n in zip(layout["skills"], (5,5,5,3)):
        click(x, layout["skill_y"], n)
    for y in layout["refresh"]:
        click(layout["x"], y)
    click(layout["x"], layout["minions"]); click(layout["x"], layout["towers"])               # minion spawn off, towers invincible
    click(layout["x"], layout["down"]); time.sleep(.5); click(layout["x"], layout["down"]); time.sleep(.5); click(layout["x"], layout["baron"])   # page 3: Spawn Baron
    click(layout["x"], layout["up"]); time.sleep(.5); click(layout["x"], layout["up"]); time.sleep(.5)            # back to page 1
    click(layout["x"], layout["teleport"]); time.sleep(.8); click(1747, 893)    # teleport, target = Baron pit on the minimap
    time.sleep(2.5)
    hover(960, 540)
    subprocess.run(["xdotool", "key", "space"], check=True)
finally:
    m.close()
# The camera-lock toggle ('y') was removed 2026-10-10: the user plays with a free camera and a locked one broke the scene.
time.sleep(1)
p = get('activeplayer')
print('level', p['level'], 'clock', round(get('gamestats')['gameTime']))
