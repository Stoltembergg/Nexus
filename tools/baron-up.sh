#!/bin/sh
# Restart the runtime, launch a practice match and bring it to the Baron-fight state (see tools/baron-setup.py).
#   sh tools/baron-up.sh            (uses whatever libraries are deployed; set CYCLE_* env to pass diagnostics through)
cd "$(dirname "$0")/.."
python3 -I tools/stop-darling-runtime.py </dev/null 2>&1 | tail -1
CYCLE_FRAME_INTERVALS=${CYCLE_FRAME_INTERVALS:-1} setsid nohup sh tools/profile-cycle.sh > /tmp/profile-cycle.log 2>&1 </dev/null &
i=0
until curl -sk -m 2 https://127.0.0.1:2999/liveclientdata/gamestats 2>/dev/null | grep -q gameTime || [ $i -gt 150 ]; do i=$((i+1)); sleep 4; done
sleep 25
hyprctl eval 'hl.dispatch(hl.dsp.window.move({x=0,y=0,window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 1
python3 -I tools/baron-setup.py | tail -2
# a restart reconnects to the same match, which the game pauses: resume it from chat
hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep .5
xdotool key Return; sleep .5; xdotool type --delay 80 '/resume'; sleep .3; xdotool key Return; sleep 2
python3 -I tools/uinput_click.py 33 443 1; sleep 1; python3 -I tools/uinput_click.py 1747 893 1; sleep 3
hyprctl eval 'hl.dispatch(hl.dsp.cursor.move({x=1500,y=950}))' >/dev/null 2>&1
sh tools/pin-game.sh >/dev/null 2>&1
t1=$(curl -sk -m3 https://127.0.0.1:2999/liveclientdata/gamestats | grep -o '[0-9.]*,\?$' | head -1); sleep 3
t2=$(curl -sk -m3 https://127.0.0.1:2999/liveclientdata/gamestats | grep -o '"gameTime": [0-9.]*')
echo "clock $t2 (was $t1) - baron fight ready"
