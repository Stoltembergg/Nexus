#!/usr/bin/env bash
# darling-lol M58i: attribute the stalled static-server client socket.
# Runs the direct UX with M58_PRES_TRACE and polls `ss -tanp` filtered to the
# dynamic static-server port at ~2 Hz, recording ESTABLISHED sockets WITH the
# owning process (ss -p shows the host-side owner: the guest's mldr). When the
# connection appears, also record birth vs loadURL time and the sizes.
set -u
work=/tmp/opencode/m58i
rm -rf "$work"; mkdir -p "$work"
/tmp/opencode/cleandarling.sh
rm -f /dev/shm/*darling-ca* /dev/shm/m58c-* /dev/shm/*cvlink* 2>/dev/null || true

setsid env -u ELECTRON_RUN_AS_NODE -u EGL_PLATFORM DISPLAY=:1 \
    darling \
    '@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client' \
    --app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229 \
    '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client' \
    --app-root='/Applications/Riot Client.app' > "$work/ux.log" 2>&1 &
lpid=$!
alive() { [ -d "/proc/$lpid" ]; }
start=$(date +%s)

(
  port=""
  while [ -e "/proc/$lpid" ]; do
    if [ -z "$port" ]; then
      port=$(grep -a -o 'Static server started on port [0-9]*' "$work/ux.log" 2>/dev/null | head -1 | grep -o '[0-9]*$')
    fi
    ts=$(date +%H:%M:%S)
    if [ -n "$port" ]; then
      out=$(ss -tanp "sport = :$port" 2>/dev/null | tail -n +2 | sed 's/Chain.*//')
      echo "$ts || $out"
    fi
    sleep 2
  done
) > "$work/tcp-attr.log" 2>&1 &

end=$((start + 300))
while [ "$(date +%s)" -lt "$end" ] && alive; do sleep 2; done
pkill -9 -x mldr 2>/dev/null; sleep 3
kill -KILL $lpid 2>/dev/null
{ pkill -9 -x mldr; pkill -9 -x darlingserver; pkill -9 -x launchd; pkill -9 -x darling; } 2>/dev/null
echo "=== ESTAB moments (first/last):"
grep -a 'ESTAB' "$work/tcp-attr.log" | head -3
echo ...
grep -a 'ESTAB' "$work/tcp-attr.log" | tail -3
echo "=== loadURL time:"; grep -a 'loadURL called' "$work/ux.log" | head -1 | cut -c1-80
