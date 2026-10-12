#!/bin/sh
# Interleaved A/B of Indium submit batching inside one match (on by default; live guest flag /tmp/metal-no-submit-batch turns it off).
#   sh tools/batch-ab.sh [rounds=4] [seconds=20] [workload args]
cd "$(dirname "$0")/.."
unset ELECTRON_RUN_AS_NODE
rounds=${1:-4}; secs=${2:-20}; shift 2 2>/dev/null
game=""
for p in /proc/[0-9]*; do a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1); case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) game=${p#/proc/};; esac; done
i=0
while [ $i -lt "$rounds" ]; do
  for mode in off on; do
    if [ $mode = off ]; then timeout 30 darling shell touch /tmp/metal-no-submit-batch > /tmp/dshell.out 2>&1 < /dev/null
    else timeout 30 darling shell rm -f /tmp/metal-no-submit-batch > /tmp/dshell.out 2>&1 < /dev/null; fi
    timeout 30 darling shell touch /tmp/metal-frame-interval-repeat > /tmp/dshell.out 2>&1 < /dev/null
    hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 2
    s0=$(awk '{print $14, $15}' /proc/$game/task/$game/stat)
    out=$(python3 -I tools/baron-workload.py "$@" --seconds "$secs" 2>/dev/null | tr -d '\n ')
    s1=$(awk '{print $14, $15}' /proc/$game/task/$game/stat)
    echo "batch=$mode cpu1=$(cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq) main_ticks_before=[$s0] after=[$s1] $out"
  done
  i=$((i+1))
done
timeout 30 darling shell rm -f /tmp/metal-no-submit-batch > /tmp/dshell.out 2>&1 < /dev/null
tail -12 ~/.darling/tmp/indium-submit-stats.log
