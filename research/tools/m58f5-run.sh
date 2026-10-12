#!/bin/sh
# darling-lol M58dx: run the stock-Electron data:-URL repro with the
# LocalFrameHost ordinal hooks injected, capturing the unperturbed dserver
# M58BC mach-post trace alongside.
set -u

ROOT=@PROJECT_ROOT@
OUT="${OUT:-/tmp/opencode/m58dx}"
HOOKS_DYLIB="${HOOKS_DYLIB:-$OUT/hooks.dylib}"
TAG="${TAG:-M58D[XY]}"
ELECTRON_APP="$HOME/.darling/Applications/Electron.app"
ELECTRON_BIN="$ELECTRON_APP/Contents/MacOS/Electron"
REPRO_HOST="${REPRO_HOST:-$ROOT/tools/m57-electron-frame-repro}"
REPRO_GUEST="/Volumes/SystemRoot$REPRO_HOST"
PROBE="$HOOKS_DYLIB"
PROBE_BUNDLE="$ELECTRON_APP/Contents/MacOS/zz-m58probe-hooks.dylib"
PROBE_GUEST="/Applications/Electron.app/Contents/MacOS/zz-m58probe-hooks.dylib"
DSERVER_LOG="$HOME/.darling/private/var/log/dserver.log"
DISPLAY="${DISPLAY:-:1}"
RUN_SECONDS="${RUN_SECONDS:-45}"

mkdir -p "$OUT"
rm -f "$OUT/electron.log" "$OUT/dserver.log"

# reset only Darling-owned processes, then bootstrap a fresh namespace
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
    DISPLAY="$DISPLAY" darling shell true >"$OUT/bootstrap.log" 2>&1
cp "$PROBE" "$PROBE_BUNDLE"

: >"$DSERVER_LOG" 2>/dev/null || true

env -u ELECTRON_RUN_AS_NODE \
    DISPLAY="$DISPLAY" DYLD_INSERT_LIBRARIES="$PROBE_GUEST" \
    darling "$ELECTRON_BIN" "$REPRO_GUEST" \
      --no-sandbox --disable-gpu-sandbox \
    >"$OUT/electron.log" 2>&1 &
launcher=$!

sleep "$RUN_SECONDS"

cp "$DSERVER_LOG" "$OUT/dserver.log" 2>/dev/null || true
ps -eo pid=,ppid=,stat=,wchan=,comm=,args= | \
    grep -E '/Applications/Electron\.app/|CrGpuMain|CrRendererMain' | grep -v grep \
    >"$OUT/processes.txt" || true

# Tear down only the repro tree (its path is unique); never darlingserver.
pkill -9 -f 'm57-electron-frame-repro\|m58f5-repro-retry' 2>/dev/null || true
kill -9 "$launcher" 2>/dev/null || true
sleep 1
rm -f "$PROBE_BUNDLE"

echo "=== M58D[XY] hook lines (electron.log) ==="
grep -aE 'M58D[XY]|M57_REPRO (dom-ready|did-finish-load|loadURL-resolved|loadURL-rejected)' "$OUT/electron.log" | head -200
echo "=== boot pids (which processes loaded the hook) ==="
grep -aoE 'M58D[XY] (boot|install) pid=[0-9]+' "$OUT/electron.log" | sort -u
echo "=== dserver M58BC to browser? (by rpid) ==="
grep -aoE 'M58BC post rpid=[0-9]+' "$OUT/dserver.log" 2>/dev/null | sort | uniq -c | sort -rn | head
echo "done"
