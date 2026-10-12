#!/usr/bin/env python3
"""Return a Practice Tool match that is already in the Baron-fight state (see baron-setup.py) to a fresh Baron fight:
revive + refresh the champion, spawn a new Baron, teleport back into the pit. Unlike baron-setup.py it does not touch
toggles (towers/minions) so it can be repeated between benchmark cases. Expects the panel on page 1."""
import json, subprocess, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uinput_click import Mouse, hover
from practice_layout import practice_layout
subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))'], check=True, stdout=subprocess.DEVNULL)
time.sleep(.5)
if json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j'])).get('class') != 'LeagueofLegends':
    sys.exit('game window is not focused')
subprocess.run(['xdotool', 'keyup', 'Alt_L', 'Alt_R', 'Control_L', 'Control_R', 'Shift_L', 'Shift_R'])
layout = practice_layout()
m = Mouse()
def click(x, y, n=1):
    if json.loads(subprocess.check_output(['hyprctl', 'activewindow', '-j'])).get('class') != 'LeagueofLegends':
        raise SystemExit('game lost focus: stopping practice setup')
    hover(x, y, settle=0.25); m.click(n)
try:
    click(layout["x"], layout["revive"])                                  # revive (no-op while alive)
    time.sleep(1.0)
    # These buttons toggle auto-refresh; clicking on every reset alternates
    # the workload between full spell spam and cooldown-limited combat.
    # Preserve the refresh settings established by baron-setup.py.
    click(layout["x"], layout["down"]); time.sleep(.5); click(layout["x"], layout["down"]); time.sleep(.5); click(layout["x"], layout["baron"])   # page 3: Spawn Baron
    click(layout["x"], layout["up"]); time.sleep(.5); click(layout["x"], layout["up"]); time.sleep(.5)                  # back to page 1
    click(layout["x"], layout["teleport"]); time.sleep(.8); click(1747, 893)                                # teleport into the pit
    time.sleep(2.5)
    hover(960, 540)
    subprocess.run(["xdotool", "key", "space"], check=True)
finally:
    m.close()
