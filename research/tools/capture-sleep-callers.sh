#!/bin/sh
# Run with sudo while a match is running: records the game main thread's nanosleep/clock_nanosleep calls
# with user call stacks, so the sleeping call sites can be identified offline.
# Read-only: kernel syscall tracepoints via perf, no ptrace, no memory reads. Starts after a 10 s countdown (switch to the game
# and play normally), records 15 s. Output: logs/sleep-callers/ (owned by the invoking user).
set -eu
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
cd "$(dirname "$0")/.."
out=logs/sleep-callers
[ ! -e "$out" ] || { echo "$out exists; move it first" >&2; exit 1; }
game=""
for p in /proc/[0-9]*; do
  a0=$(tr '\0' '\n' < "$p/cmdline" 2>/dev/null | head -1)
  case "$a0" in */LeagueofLegends) game=${p#/proc/};; esac
done
[ -n "$game" ] || { echo "no game process" >&2; exit 1; }
mkdir -p "$out"
cp "/proc/$game/maps" "$out/maps.txt"
echo "game pid $game; recording in 10 s (switch to the game and play), 15 s long"
sleep 10
perf record -q -a -g --call-graph fp --clockid mono -o "$out/sleep.data" \
  -e raw_syscalls:sys_enter --filter "common_pid == $game && (id == 35 || id == 230 || id == 23 || id == 270 || id == 7)" \
  -e raw_syscalls:sys_exit --filter "common_pid == $game && (id == 35 || id == 230 || id == 23 || id == 270 || id == 7)" \
  -- sleep 15
chown -R "${SUDO_UID:-0}:${SUDO_GID:-0}" "$out"
echo done: "$out"
