#!/bin/sh
# Give the main thread a physical core of its own. GAME_MAIN_CPU=9 tests the
# other preferred core of this laptop; the default remains CPU 1.
main_cpu=${GAME_MAIN_CPU:-1}
case "$main_cpu" in
 1) worker_cpus=2-11 ;;
 9) worker_cpus=0-7,10-11 ;;
 *) echo "GAME_MAIN_CPU must be 1 or 9" >&2; exit 1 ;;
esac
g=""
for p in /proc/[0-9]*; do
  case "$(tr '\0' '\n' 2>/dev/null < "$p/cmdline" | head -1)" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) g=${p#/proc/};; esac
done
[ -n "$g" ] || { echo "no game"; exit 1; }
for p in $(pgrep -u "$USER" -f 'darlingserver|t3code|zen-bin|Isolated Web|LeagueClient|RiotClient|Riot Client|waybar'); do
  for t in /proc/$p/task/*; do taskset -pc "$worker_cpus" "${t##*/}" >/dev/null 2>&1; done
done
for t in /proc/$g/task/*; do taskset -pc "$worker_cpus" "${t##*/}" >/dev/null 2>&1; done
taskset -pc "$main_cpu" "$g"
# Fullscreen the (already 1920x1080) game window so Hyprland scans it out directly (render.direct_scanout = 1) instead
# of compositing it (~10% of the GPU). A fullscreen window *rule* at creation gives a black window: do it afterwards.
if hyprctl clients -j 2>/dev/null | python3 -I -c "
import json,sys
sys.exit(0 if any(c.get('class')=='LeagueofLegends' and not c.get('fullscreen') for c in json.load(sys.stdin)) else 1)"; then
  hyprctl eval 'hl.dispatch(hl.dsp.window.fullscreen({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1
fi
