#!/usr/bin/env bash
# darling-lol M58f4: long UX soak — does the login view render after splash?
# Group-safe runner (setsid, /proc liveness, guest-pkill teardown), scrot
# screenshots every ~90 s, milestone/event log, dserver + mldr monitoring.
set -u
work=/tmp/opencode/m58f4
rm -rf "$work"; mkdir -p "$work"
/tmp/opencode/cleandarling.sh
rm -f /dev/shm/*darling-ca* /dev/shm/m58c-* /dev/shm/*cvlink* 2>/dev/null || true

setsid env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:1 M58_PRES_TRACE=1 \
    darling \
    '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client' \
    --app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229 \
    '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client' \
    --app-root='/Applications/Riot Client.app' > "$work/ux.log" 2>&1 &
lpid=$!
alive() { [ -d "/proc/$lpid" ]; }
start=$(date +%s)

# dserver/mldr sampler
(
  while [ -e "/proc/$lpid" ]; do
    ds=$(pgrep -x darlingserver | head -1)
    echo "$(date +%H:%M:%S) dserver=$([ -n "$ds" ] && echo alive || echo DEAD) mldr=$(pgrep -c -x mldr)"
    sleep 2
  done
) > "$work/monitor.log" 2>&1 &

# milestone watcher
(
  tail -f -n 0 "$work/ux.log" 2>/dev/null | while read -r line; do
    case "$line" in
      *whenReady*) echo "$(date +%H:%M:%S) MS whenReady-resolved" ;;
      *"calling createWindow"*) echo "$(date +%H:%M:%S) MS createWindow" ;;
      *"loadURL called"*) echo "$(date +%H:%M:%S) MS loadURL" ;;
      *"Splash screen is ready"*) echo "$(date +%H:%M:%S) MS splash-ready" ;;
      *"dom-ready"*|*"dom-ready"*) echo "$(date +%H:%M:%S) MS dom-ready" ;;
      *"did-finish-load"*|*"did-finish"*) echo "$(date +%H:%M:%S) MS did-finish-load" ;;
      *"Finished page load"*|*"page loaded"*) echo "$(date +%H:%M:%S) MS page-load" ;;
      *LOLSIGFAIL*) echo "$(date +%H:%M:%S) EVENT $(echo "$line" | cut -c1-90)" ;;
      *"BAD SEND"*) echo "$(date +%H:%M:%S) EVENT bad-send" ;;
      *Chev*) : ;;
    esac
  done
) > "$work/milestones.log" 2>&1 &

# screenshots: 60,100,140,...,400 s
for t in 60 100 140 180 220 260 300 340 400; do
  target=$((start + t))
  while [ "$(date +%s)" -lt "$target" ] && alive; do sleep 2; done
  DISPLAY=:1 scrot -D :1 "$work/shot-$t.png" 2>/dev/null
done &

end=$((start + 420))
while [ "$(date +%s)" -lt "$end" ] && alive; do sleep 2; done
pkill -9 -x mldr 2>/dev/null; sleep 3
kill -TERM $lpid 2>/dev/null; sleep 5; kill -KILL $lpid 2>/dev/null
pkill -9 -x mldr; pkill -9 -x darlingserver; pkill -9 -x launchd; pkill -9 -x darling
echo "=== milestones:"; cat "$work/milestones.log" 2>/dev/null | head -25
echo "=== screenshots:"; ls -la "$work"/shot-*.png 2>/dev/null | awk '{print $5, $9}'
echo "=== last ux.log lines:"; tail -5 "$work/ux.log"
