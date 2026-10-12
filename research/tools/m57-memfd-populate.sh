#!/bin/sh
# darling-lol M57bk: does the creator's write reach the shared memfd?
#
# Polls every darling-mementry memfd rapidly from the HOST while the stock
# Electron repro runs, recording size + non-zero byte count over time, so we can
# see whether a region is ever populated (and stays populated) after the browser
# maps it. No guest-side instrumentation.
set -u

work=/tmp/opencode/m57-pop-run
out=/tmp/opencode/m57-pop-samples.log
chromium_log=/tmp/opencode/m57-ipcz.log
capture_seconds=${M57_TRACE_SECONDS:-40}
interval=${M57_POLL_INTERVAL:-0.05}
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

cleanup
rm -rf "$work"; mkdir -p "$work"; cd "$work" || exit 1
rm -f "$chromium_log"

env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM -u DYLD_INSERT_LIBRARIES \
    DISPLAY=:99 darling shell true >/tmp/opencode/m57-pop-boot.log 2>&1
DISPLAY=:99 timeout "$((capture_seconds + 10))" env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM -u DYLD_INSERT_LIBRARIES \
    darling "$bin" --no-sandbox >"$chromium_log" 2>&1 &
launcher=$!

start=$(date +%s.%N)
while :; do
    now=$(date +%s.%N)
    elapsed=$(awk -v a="$start" -v b="$now" 'BEGIN{print b-a}')
    awk -v e="$elapsed" -v c="$capture_seconds" 'BEGIN{exit !(e>=c)}' && break

    for pid in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ -d "/proc/$pid/fd" ] || continue
        for fd in $(ls "/proc/$pid/fd" 2>/dev/null); do
            tgt=$(readlink "/proc/$pid/fd/$fd" 2>/dev/null) || continue
            case "$tgt" in
                *memfd:darling-mementry*)
                    sz=$(stat -Lc %s "/proc/$pid/fd/$fd" 2>/dev/null) || continue
                    # Count non-zero bytes across the whole region (capped).
                    nz=$(head -c 262144 "/proc/$pid/fd/$fd" 2>/dev/null | tr -d '\0' | wc -c)
                    printf '%s pid=%s fd=%s size=%s nonzero=%s\n' \
                        "$elapsed" "$pid" "$fd" "$sz" "$nz" >> "$out"
                    ;;
            esac
        done
    done

    sleep "$interval"
done

kill -9 "$launcher" 2>/dev/null
wait "$launcher" 2>/dev/null

echo "=== distinct (fd,size,nonzero) observations ==="
awk '{print $3, $4, $5}' "$out" | sort -u
echo "=== corruption lines ==="
grep -a "Corruption detected" "$chromium_log" || echo "(none)"
