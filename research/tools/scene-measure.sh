#!/bin/sh
# Frame statistics of the Baron workload plus main-thread user/sys share, darlingserver CPU and GPU load in the same window.
#   sh tools/scene-measure.sh <label> <seconds> [workload args]
cd "$(dirname "$0")/.."
unset ELECTRON_RUN_AS_NODE
label=$1; secs=$2; shift 2
game=""
for p in /proc/[0-9]*; do a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1); case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) game=${p#/proc/};; esac; done 2>/dev/null
server=$(pgrep -x darlingserver | head -1)
timeout 30 darling shell touch /tmp/metal-frame-interval-repeat > /tmp/dshell.out 2>&1 < /dev/null
hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 1
( sleep 1; a=$(awk '{print $14, $15}' /proc/$game/task/$game/stat); sa=$(awk '{print $14+$15}' /proc/$server/stat); t0=$(date +%s.%N); n=0; s=0
  while [ $n -lt $((secs-2)) ]; do s=$((s+$(cat /sys/class/drm/card1/device/gpu_busy_percent))); n=$((n+1)); sleep 1; done
  b=$(awk '{print $14, $15}' /proc/$game/task/$game/stat); sb=$(awk '{print $14+$15}' /proc/$server/stat)
  echo "$a $b $t0 $(date +%s.%N) $sa $sb $((s/n)) $(cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq)" | awk '{w=($6-$5)*100; printf "main user %.0f%% sys %.0f%% idle %.0f%% | server %.0f%% | gpu %d%% | %.1f GHz", 100*($3-$1)/w, 100*($4-$2)/w, 100-100*($3-$1+$4-$2)/w, 100*($8-$7)/w, $9, $10/1e6}' > /tmp/scene-cpu ) &
out=$(python3 -I tools/baron-workload.py "$@" --seconds "$secs" 2>/dev/null | tr -d '\n ' | sed 's/"mean_ms[^,]*,//; s/"worst_ms.*//; s/"frames":[0-9]*,"seconds":[0-9.]*,//')
wait
echo "$label | $out | $(cat /tmp/scene-cpu)"
