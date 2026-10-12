#!/bin/sh
# Who uses CPU during a Baron fight: processes above 2% and game threads above 2%, plus per-CPU clocks. For comparing a
# fresh match with a reconnected one.   sh tools/load-snapshot.sh [seconds=12]
cd "$(dirname "$0")/.."
secs=${1:-12}
game=""
for p in /proc/[0-9]*; do a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1); case "$a0" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) game=${p#/proc/};; esac; done 2>/dev/null
hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1
(python3 -I tools/baron-workload.py --seconds $((secs+6)) > /tmp/load-wl.txt 2>&1 &)
sleep 3
pidstat -u $secs 1 2>/dev/null | grep Moyenne | awk '{c=$8; gsub(",",".",c); if (c+0>=2) printf "  proc %6.1f%%  %s\n", c, $NF}' | sort -t' ' -k4 -rn | sort -k2 -rn > /tmp/load-procs.txt &
pidstat -t -p $game $secs 1 2>/dev/null | grep Moyenne | awk '{c=$(NF-2); gsub(",",".",c); if (c+0>=2 && $4!="-") printf "  thread %6.1f%%  tid %s %s\n", c, $4, $NF; else if (c+0>=2 && $4=="-") printf "  thread %6.1f%%  tid %s %s\n", c, $5, $NF}' | sort -k2 -rn > /tmp/load-threads.txt &
mpstat $secs 1 2>/dev/null | awk '/Moyenne/{u=$3; s=$5; i=$NF; print "  all CPUs: user "u"% sys "s"% idle "i"%"}' > /tmp/load-all.txt &
n=0; : > /tmp/load-freq.txt
while [ $n -lt $secs ]; do cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq >> /tmp/load-freq.txt; n=$((n+1)); sleep 1; done
wait
cat /tmp/load-all.txt; awk '{s+=$1} END{printf "  cpu1 clock mean %.2f GHz over %d samples\n", s/NR/1e6, NR}' /tmp/load-freq.txt
echo "  Tctl $(sensors | awk '/Tctl/{print $2}')  PPT $(sensors | awk '/PPT/{print $2 $3}')"
cat /tmp/load-procs.txt; cat /tmp/load-threads.txt
sleep 8; tr -d '\n ' < /tmp/load-wl.txt | grep -o '"fps":[0-9.]*,"mean_ms":[0-9.]*,"p50_ms":[0-9.]*,"p95_ms":[0-9.]*,"p99_ms":[0-9.]*'; echo
