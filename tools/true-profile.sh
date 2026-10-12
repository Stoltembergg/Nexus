#!/bin/sh
# Whole-stack profile of a running League match with standard Linux tools. Run with sudo while you are playing:
#
#   sudo sh tools/true-profile.sh [seconds=30]
#
# After a 10 s countdown (switch to the game and play: fight, move the camera, use abilities) it records, in parallel:
#   perf-game.data      on-CPU samples of the game's main thread, user + kernel stacks (perf record -g, 999 Hz)
#   perf-server.data   same for darlingserver (the RPC server) and LeagueClient
#   offcpu.data         scheduler switch-out/in events of the main thread with stacks (where and how long it blocks)
#   perf-stat.txt       hardware counters: cycles, instructions (IPC), cache/branch misses, context switches, faults
#   syscalls.txt        bpftrace: per-syscall count and total time of the main thread (needs bpftrace)
#   offcputime.txt      bcc offcputime: blocked time by stack (needs bcc)
#   runqlat.txt         bcc runqlat: scheduler run-queue latency of the game (needs bcc)
#   gpu.json            amdgpu_top: GPU engine load, clocks, power per 0.5 s (needs amdgpu_top)
#   turbostat.txt       per-core frequency, package/core power and temperature
#   pidstat.txt         per-thread CPU of the game and the server (needs sysstat)
# plus the /proc maps, kallsyms and sysfs power state. Nothing here attaches a debugger or reads process memory.
# Output goes to logs/true-profile-<time>/, owned by the invoking user.
set -u
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/.."
secs=${1:-30}
out=logs/true-profile-$(date +%H%M%S)
mkdir -p "$out"

game=""; server=""; client=""
for p in /proc/[0-9]*; do
  a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1)
  case "$a0" in
    */LeagueofLegends) game=${p#/proc/};;
    */LeagueClient) client=${p#/proc/};;
    *darlingserver) [ -z "$server" ] && server=${p#/proc/};;
  esac
done
[ -n "$game" ] || { echo "no game process: start a match first" >&2; exit 1; }
echo "game=$game server=$server client=$client out=$out"
echo "game=$game server=$server client=$client" > "$out/pids.txt"
cp "/proc/$game/maps" "$out/game-maps.txt"
[ -n "$server" ] && cp "/proc/$server/maps" "$out/server-maps.txt"
cp /proc/kallsyms "$out/kallsyms.txt" 2>/dev/null
{ echo "uname: $(uname -r)"; for f in /sys/class/drm/card1/device/power_dpm_force_performance_level /sys/firmware/acpi/platform_profile /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor; do echo "$f: $(cat $f 2>/dev/null)"; done; } > "$out/state.txt"

echo "recording starts in 10 s: switch to the game and play for $((secs + 10)) s"
sleep 10
t=$secs
pids=""
bg() { "$@" & pids="$pids $!"; }

bg perf record -q -F 999 -g --call-graph fp --clockid mono -t "$game" -o "$out/perf-game.data" -- sleep "$t"
[ -n "$server" ] && bg perf record -q -F 499 -g --call-graph fp --clockid mono -p "$server${client:+,$client}" -o "$out/perf-server.data" -- sleep "$t"
bg perf record -q --call-graph fp --clockid mono -e sched:sched_switch --filter "prev_pid == $game || next_pid == $game" \
   -e sched:sched_wakeup --filter "pid == $game" -a -o "$out/offcpu.data" -- sleep "$t"
bg perf stat -x, -e cycles,instructions,cache-misses,branch-misses,context-switches,cpu-migrations,page-faults -t "$game" -o "$out/perf-stat.txt" -- sleep "$t"
bg turbostat --quiet --interval 1 --num_iterations "$t" --show Core,CPU,Avg_MHz,Bzy_MHz,Busy%,PkgWatt,CorWatt,GFXWatt,CoreTmp,PkgTmp -o "$out/turbostat.txt"
command -v pidstat >/dev/null && bg sh -c "pidstat -t -p $game${server:+,$server} 1 $t > '$out/pidstat.txt'"
command -v amdgpu_top >/dev/null && bg sh -c "amdgpu_top --json -s 500 -n $((t * 2)) > '$out/gpu.json' 2> '$out/gpu.err'"
if [ "${PROFILE_SYSCALLS:-0}" = 1 ] && command -v bpftrace >/dev/null; then  # costly (HPET timestamps on every syscall): opt-in
  cat > "$out/syscalls.bt" <<BT
tracepoint:raw_syscalls:sys_enter /pid == $game && tid == $game/ { @start = nsecs; @nr = args->id; }
tracepoint:raw_syscalls:sys_exit /pid == $game && tid == $game && @start/ { @ns[@nr] = sum(nsecs - @start); @calls[@nr] = count(); @max[@nr] = max(nsecs - @start); @start = 0; }
interval:s:$t { exit(); }
BT
  bg sh -c "bpftrace '$out/syscalls.bt' > '$out/syscalls.txt' 2>&1"
fi
BCC=/usr/share/bcc/tools
[ -x "$BCC/offcputime" ] && bg sh -c "$BCC/offcputime -t $game -f -U -K -m 20 $t > '$out/offcputime.txt' 2>&1"
[ -x "$BCC/runqlat" ] && bg sh -c "$BCC/runqlat -p $game -m $t 1 > '$out/runqlat.txt' 2>&1"
wait $pids 2>/dev/null
chown -R "${SUDO_UID:-0}:${SUDO_GID:-0}" "$out"
echo "done: $out"
ls -l "$out" | awk 'NR>1{print $5, $9}'
