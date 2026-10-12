#!/bin/sh
set -eu

work=/tmp/opencode/m57-ipcz-run
capture_seconds=${M57_TRACE_SECONDS:-45}
script_dir=$(cd -- "$(dirname "$0")" && pwd)
# M57_APP=riot runs the real Riot client (which loads web content); the default
# stock Electron has no app path and never loads a page, so it has no frames.
if [ "${M57_APP:-electron}" = "riot" ]; then
    app="$HOME/.darling/Applications/Riot Client.app"
    bin="$app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client"
    dylib="$app/Contents/Frameworks/Riot Client.app/Contents/MacOS/zz-m57-ipcz-trace.dylib"
    guest_dylib="/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/zz-m57-ipcz-trace.dylib"
    app_args="${M57_RIOT_ARGS:---appPort=9091 --remotingAuthToken=developer --appPid=1 --logDir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client --userDataRoot=@GUEST_HOME@/Library/Application Support/Riot Games/Riot Client --crashpadEnvironment=development --machineId=developer --sessionId=direct --use-gl=desktop --enable-hardware-acceleration}"
    # Without these the Riot app hangs in Sentry/logger init before createWindow.
    app_env="RC_TEST_MODE=1 SENTRY_DSN= SENTRY_ENVIRONMENT=test ${M57_EXTRA_ENV:-}"
else
    app="$HOME/.darling/Applications/Electron.app"
    bin="$app/Contents/MacOS/Electron"
    dylib="$app/Contents/MacOS/zz-m57-ipcz-trace.dylib"
    guest_dylib="/Applications/Electron.app/Contents/MacOS/zz-m57-ipcz-trace.dylib"
    repro_host=$(cd -- "$script_dir/m57-electron-frame-repro" && pwd)
    app_args="/Volumes/SystemRoot$repro_host --no-sandbox --disable-gpu-sandbox"
    app_env=""
fi

clang -target x86_64-apple-macosx11.0 -fuse-ld=lld -dynamiclib \
    -nostdlib -nodefaultlibs -undefined dynamic_lookup \
    -o /tmp/opencode/m57-ipcz-trace.dylib "$script_dir/m57-ipcz-trace.c" \
    -Wl,-install_name,/tmp/m57-ipcz-trace.dylib
cleanup() {
    env -u DYLD_INSERT_LIBRARIES -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM \
        DISPLAY=:99 darling shell /bin/rm -f "$guest_dylib" >/dev/null 2>&1 || true
    rm -f "$dylib"
}
trap cleanup EXIT INT TERM

attempt=0
while [ "$attempt" -lt 5 ]; do
    attempt=$((attempt + 1))
    pids=$(ps -eo pid=,comm= | awk '$2=="mldr"||$2=="darlingserver"||$2=="launchd"||$2=="shellspawn"||$2=="launchctl"||$2=="memberd"{print $1}')
    [ -z "$pids" ] && break
    for pid in $pids; do kill -9 "$pid" 2>/dev/null || true; done
    sleep 1
done
if pgrep -x 'mldr|darlingserver|launchd|shellspawn|launchctl|memberd' >/dev/null; then
    echo "Darling reset failed: scoped processes are still running" >&2
    exit 1
fi
rm -f "$HOME/.darling/.init.pid" /tmp/m57-ipcz.bin /tmp/m57-ipcz-status.bin /tmp/opencode/m57-ipcz.log
rm -rf "$work"
mkdir -p "$work"
cd "$work"
# Bootstrap Darling without DYLD injection. On a cold prefix, launchd and other
# infrastructure inherit the launch environment and must not load this probe.
env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:99 darling shell true \
    >/tmp/opencode/m57-ipcz-bootstrap.log 2>&1
env -u DYLD_INSERT_LIBRARIES -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM \
    DISPLAY=:99 darling shell /bin/cp \
    /Volumes/SystemRoot/tmp/opencode/m57-ipcz-trace.dylib "$guest_dylib" \
    >/tmp/opencode/m57-ipcz-copy.log 2>&1
# Optional DYLD_LIBRARY_PATH for the Electron launch only (e.g. to force the
# app-bundled ANGLE libEGL instead of Darling's /usr/lib/native/libEGL.dylib).
if [ -n "${M57_DYLD_LIBRARY_PATH:-}" ]; then
    env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:99 \
        DYLD_INSERT_LIBRARIES="$guest_dylib" $app_env \
        DYLD_LIBRARY_PATH="$M57_DYLD_LIBRARY_PATH" \
        timeout ${M57_APP_TIMEOUT:-50} darling "$bin" $app_args >/tmp/opencode/m57-ipcz.log 2>&1 &
else
    env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:99 \
        DYLD_INSERT_LIBRARIES="$guest_dylib" $app_env \
        timeout ${M57_APP_TIMEOUT:-50} darling "$bin" $app_args >/tmp/opencode/m57-ipcz.log 2>&1 &
fi
launcher=$!
# `darling` returns after shellspawn launches the guest; keep both the dylib and
# this script alive while Electron and its helper processes initialize.
sleep "$capture_seconds"
kill -9 "$launcher" 2>/dev/null || true
# Reap if it exits promptly; do not let a setuid Darling launcher hold cleanup.
wait "$launcher" 2>/dev/null || true

if [ ! -s /tmp/m57-ipcz.bin ]; then
    if [ -s /tmp/m57-ipcz-status.bin ]; then
        od -An -tx8 -v /tmp/m57-ipcz-status.bin >&2
    fi
    echo "no ipcz records captured; inspect /tmp/opencode/m57-ipcz.log" >&2
    exit 1
fi
python3 "$script_dir/m57-ipcz-trace.py" /tmp/m57-ipcz.bin
