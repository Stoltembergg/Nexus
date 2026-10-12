#!/usr/bin/env bash
# darling-lol M58p: is the UX browser main-thread loop blocked BY the renderer?
#
# Measures the browser main-process event loop with
# tools/m58n-browser-loop-latency.py, then SIGKILLs the renderer processes
# and measures again. In 2026-09-23 runs the loop was seconds-slow before
# (setTimeout1000 2228 ms, fs 13375 ms) and completely normal after
# (setTimeout1000 1180 ms, fs 286 ms), so the browser main thread is
# blocked by/for the renderer. That block is what starves the app's own
# Node/Express asset server and keeps the window from ever loading.
set -u
PROBE="$(cd "$(dirname "$0")" && pwd)/m58n-browser-loop-latency.py"
/tmp/opencode/cleandarling.sh >/dev/null 2>&1

setsid env DISPLAY=:1 darling \
    '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client' \
    --app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229 \
    --enableHardwareAcceleration \
    '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client' \
    --app-root='/Applications/Riot Client.app' > /tmp/opencode/m58p-ux.log 2>&1 &
lpid=$!

sleep 100
echo "renderers: $(pgrep -x CrRendererMain | tr '\n' ' ')"
echo "=== loop BEFORE ==="
timeout 80 python3 "$PROBE" 2>&1 | head -2

for p in $(pgrep -x CrRendererMain); do kill -9 "$p" && echo "killed $p"; done
sleep 8
echo "=== loop AFTER ==="
timeout 80 python3 "$PROBE" 2>&1 | head -2
echo "=== loop AFTER (sanity) ==="
timeout 80 python3 "$PROBE" 2>&1 | head -2

kill -9 $lpid 2>/dev/null
pkill -9 -x mldr 2>/dev/null; pkill -9 -x darlingserver 2>/dev/null
pkill -9 -x launchd 2>/dev/null; pkill -9 -x darling 2>/dev/null
/tmp/opencode/cleandarling.sh >/dev/null 2>&1
echo "done"
