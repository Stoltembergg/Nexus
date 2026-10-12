#!/bin/sh
# darling-lol M57bi: host-only shared-memory poll.
#
# Purpose: observe Darling's shared-memory regions (memfd:darling-mementry)
# from the HOST while the stock-Electron repro runs, WITHOUT any guest-side
# instrumentation (in-process hooks on the hot allocator/map paths perturb
# startup and invalidate the run).
#
# For every process we find, sample each darling-mementry memfd: size and the
# number of non-zero bytes in the first 4 KiB. Correlate the samples with the
# Chromium log's "Corruption detected" timestamp.
#
# Usage: M57_TRACE_SECONDS=40 tools/m57-memfd-poll.sh
set -u

work=/tmp/opencode/m57-memfd-run
out=/tmp/opencode/m57-memfd-samples.log
chromium_log=/tmp/opencode/m57-ipcz.log
capture_seconds=${M57_TRACE_SECONDS:-40}
interval=${M57_POLL_INTERVAL:-0.2}
app="$HOME/.darling/Applications/Electron.app"
bin="$app/Contents/MacOS/Electron"

: > "$out"

cleanup() {
    ps -eo pid,comm | awk '$2=="mldr"||$2=="darlingserver"||$2=="launchd"||$2=="shellspawn"||$2=="launchctl"||$2=="memberd"{print $1}' \
        | while read -r p; do kill -9 "$p" 2>/dev/null; done
    sleep 1
    rm -f "$HOME/.darling/.init.pid"
}
trap cleanup EXIT INT TERM

# Reset the Darling container.
cleanup
rm -rf "$work"; mkdir -p "$work"; cd "$work" || exit 1
rm -f "$chromium_log"

# Bootstrap without any injection, then launch stock Electron.
env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM -u DYLD_INSERT_LIBRARIES \
    DISPLAY=:99 darling shell true >/tmp/opencode/m57-memfd-boot.log 2>&1
DISPLAY=:99 timeout "$((capture_seconds + 10))" env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM -u DYLD_INSERT_LIBRARIES \
    darling "$bin" --no-sandbox >"$chromium_log" 2>&1 &
launcher=$!

start=$(date +%s.%N)
while :; do
    now=$(date +%s.%N)
    elapsed=$(awk -v a="$start" -v b="$now" 'BEGIN{print b-a}')
    awk -v e="$elapsed" -v c="$capture_seconds" 'BEGIN{exit !(e>=c)}' && break

    # Enumerate every candidate process and sample its darling-mementry memfds.
    for pid in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ -d "/proc/$pid/fd" ] || continue
        for fd in $(ls "/proc/$pid/fd" 2>/dev/null); do
            tgt=$(readlink "/proc/$pid/fd/$fd" 2>/dev/null) || continue
            case "$tgt" in
                *memfd:darling-mementry*)
                    sz=$(stat -Lc %s "/proc/$pid/fd/$fd" 2>/dev/null) || continue
                    nz=$(head -c 4096 "/proc/$pid/fd/$fd" 2>/dev/null | tr -d '\0' | wc -c)
                    comm=$(cat "/proc/$pid/comm" 2>/dev/null)
                    printf '%s pid=%s comm=%s fd=%s size=%s nonzero4k=%s\n' \
                        "$elapsed" "$pid" "$comm" "$fd" "$sz" "$nz" >> "$out"
                    ;;
            esac
        done
    done

    sleep "$interval"
done

kill -9 "$launcher" 2>/dev/null
wait "$launcher" 2>/dev/null

echo "=== samples ==="
cat "$out"
echo "=== corruption lines ==="
grep -a "Corruption detected" "$chromium_log" || echo "(none)"
