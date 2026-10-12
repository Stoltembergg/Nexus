#!/bin/sh
# Interleaved A/B of a live Indium guest flag inside one match. The flag file's presence is the "off" (A) state.
#   sh tools/flag-ab.sh <guest flag path> [rounds=3] [seconds=20] [workload args]
#   e.g. sh tools/flag-ab.sh /tmp/metal-no-lazy-pass 3 20 --hover
cd "$(dirname "$0")/.."
unset ELECTRON_RUN_AS_NODE
flag=$1; rounds=${2:-3}; secs=${3:-20}; shift 3 2>/dev/null
game=""
for p in /proc/[0-9]*; do a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1); case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) game=${p#/proc/};; esac; done 2>/dev/null
i=0
while [ $i -lt "$rounds" ]; do
  for mode in off on; do
    if [ $mode = off ]; then timeout 30 darling shell touch "$flag" > /tmp/dshell.out 2>&1 < /dev/null
    else timeout 30 darling shell rm -f "$flag" > /tmp/dshell.out 2>&1 < /dev/null; fi
    timeout 30 darling shell touch /tmp/metal-frame-interval-repeat > /tmp/dshell.out 2>&1 < /dev/null
    hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 2
    (n=0; s=0; while [ $n -lt "$secs" ]; do s=$((s+$(cat /sys/class/drm/card1/device/gpu_busy_percent))); n=$((n+1)); sleep 1; done; echo $((s/n)) > /tmp/flag-ab-gpu) &
    a=$(awk '{print $14, $15}' /proc/$game/task/$game/stat); t0=$(date +%s.%N)
    ( sleep "$secs"; b=$(awk '{print $14, $15}' /proc/$game/task/$game/stat); echo "$a $b $t0 $(date +%s.%N)" | awk '{w=($6-$5)*100; printf "main user %.0f%% sys %.0f%%", 100*($3-$1)/w, 100*($4-$2)/w}' > /tmp/flag-ab-cpu ) &
    out=$(python3 -I tools/baron-workload.py "$@" --seconds "$secs" 2>/dev/null | tr -d '\n ' | sed 's/"worst_ms.*baron_hp_bar_px_start/"hp/')
    echo "feature=$mode $(cat /tmp/flag-ab-cpu) gpu $(cat /tmp/flag-ab-gpu)% $(tail -1 ~/.darling/tmp/indium-submit-stats.log | cut -d' ' -f3-) $out"
  done
  i=$((i+1))
done
timeout 30 darling shell rm -f "$flag" > /tmp/dshell.out 2>&1 < /dev/null
