#!/bin/sh
set -eu

electron_app="$HOME/.darling/Applications/Electron.app"
electron_bin="$electron_app/Contents/MacOS/Electron"
repro_host=$(cd -- "$(dirname "$0")/m57-electron-frame-repro" && pwd)
repro_guest="/Volumes/SystemRoot$repro_host"
output_dir=${M57_REPRO_OUTPUT_DIR:-/tmp/opencode/m57-frame-repro}
display=${DISPLAY:-:99}
run_seconds=${M57_REPRO_SECONDS:-30}
extra_args=${M57_REPRO_EXTRA_ARGS:-}
probe_host=${M57_REPRO_DYLIB:-}
probe_bundle="$electron_app/Contents/MacOS/zz-m57-repro-probe.dylib"
probe_guest="/Applications/Electron.app/Contents/MacOS/zz-m57-repro-probe.dylib"

if [ ! -x "$electron_bin" ]; then
    echo "missing Electron 22.3.27 binary: $electron_bin" >&2
    exit 1
fi

mkdir -p "$output_dir"
rm -f "$output_dir/electron.log" "$output_dir/windows.txt" \
    "$output_dir/window.xwd" "$output_dir/window.png"

# Runs after interrupted experiments often leave a stale container namespace or
# orphaned mldr processes. Reset only Darling-owned processes, then bootstrap a
# clean namespace before launching Electron.
attempt=0
while [ "$attempt" -lt 5 ]; do
    attempt=$((attempt + 1))
    pids=$(ps -eo pid=,comm= | awk '$2=="mldr"||$2=="darlingserver"||$2=="launchd"||$2=="shellspawn"||$2=="launchctl"||$2=="memberd"{print $1}')
    [ -z "$pids" ] && break
    for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
    sleep 1
done
rm -f "$HOME/.darling/.init.pid"
env -u DYLD_INSERT_LIBRARIES -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM \
    DISPLAY="$display" darling shell true >"$output_dir/bootstrap.log" 2>&1

launch_env=""
if [ -n "$probe_host" ]; then
    cp "$probe_host" "$probe_bundle"
    launch_env="DYLD_INSERT_LIBRARIES=$probe_guest"
fi

env -u DYLD_INSERT_LIBRARIES -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM \
    DISPLAY="$display" $launch_env \
    timeout "$run_seconds" darling "$electron_bin" "$repro_guest" \
    --no-sandbox --disable-gpu-sandbox $extra_args \
    >"$output_dir/electron.log" 2>&1 &
launcher=$!

elapsed=0
window_id=""
while [ "$elapsed" -lt "$run_seconds" ]; do
    DISPLAY="$display" xwininfo -root -tree >"$output_dir/windows.txt" 2>&1 || true
    window_id=$(awk '/"M57 Electron Frame Repro"/ { print $1; exit }' "$output_dir/windows.txt")
    [ -z "$window_id" ] || break
    sleep 2
    elapsed=$((elapsed + 2))
done
if [ -n "$window_id" ] && command -v xwd >/dev/null 2>&1; then
    DISPLAY="$display" xwd -id "$window_id" -silent -out "$output_dir/window.xwd" 2>/dev/null || true
    # Capture again later in the run so post-load frames are visible.
    capture_interval=$(( (run_seconds + 2) / 3 ))
    i=1
    while [ "$((i * capture_interval))" -lt "$run_seconds" ]; do
        sleep "$capture_interval"
        DISPLAY="$display" xwd -id "$window_id" -silent \
            -out "$output_dir/window-late-$i.xwd" 2>/dev/null || true
        i=$((i + 1))
    done
fi
curl -fsS --max-time 2 http://127.0.0.1:9222/json \
    >"$output_dir/devtools-targets.json" 2>/dev/null || true
env -u DYLD_INSERT_LIBRARIES -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM \
    DISPLAY="$display" darling shell /usr/bin/curl -fsS --max-time 3 \
    http://127.0.0.1:9222/json >"$output_dir/devtools-targets-guest.json" \
    2>"$output_dir/devtools-curl-guest.log" || true
ps -eo pid=,ppid=,stat=,wchan=,comm=,args= | \
    grep -E '/Applications/Electron\.app/|CrGpuMain' | grep -v grep \
    >"$output_dir/processes.txt" || true
if [ -s "$output_dir/window.xwd" ] && command -v convert >/dev/null 2>&1; then
    convert "$output_dir/window.xwd" "$output_dir/window.png" 2>/dev/null || true
    for xwd in "$output_dir"/window-late-*.xwd; do
        [ -f "$xwd" ] || continue
        convert "$xwd" "${xwd%.xwd}.png" 2>/dev/null || true
    done
fi

remaining=$((run_seconds - elapsed))
[ "$remaining" -le 0 ] || sleep "$remaining"
guest_pids=$(pgrep -f '^/Applications/Electron\.app/.*m57-electron-frame-repro' || true)
[ -z "$guest_pids" ] || kill -9 $guest_pids 2>/dev/null || true
kill -9 "$launcher" 2>/dev/null || true
wait "$launcher" 2>/dev/null || true
rm -f "$probe_bundle"

echo "log: $output_dir/electron.log"
echo "windows: $output_dir/windows.txt"
[ -s "$output_dir/window.png" ] && echo "screenshot: $output_dir/window.png"
grep -aE 'M57_REPRO|ERROR|FATAL|Corruption|eglCreateContext|SharedImageStub' \
    "$output_dir/electron.log" | grep -av 'set env:' | sort -u || true
