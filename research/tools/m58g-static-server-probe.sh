#!/usr/bin/env bash
# darling-lol M58g: name the stall point of the script-stream data path.
# Polls: (1) TCP state against the UX's dynamic static-server port (does the
# renderer's fetch reach it? does data flow?), (2) window tree + window-level
# captures (full-screen scrot is blank even with windows up), and records the
# usual milestones.
set -u
work=/tmp/opencode/m58g
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

# 1 Hz TCP poller against the dynamic static-server port
(
  port=""
  while [ -e "/proc/$lpid" ]; do
    if [ -z "$port" ]; then
      port=$(grep -a -o 'Static server started on port [0-9]*' "$work/ux.log" 2>/dev/null | head -1 | grep -o '[0-9]*$')
    fi
    ts=$(date +%H:%M:%S)
    if [ -n "$port" ]; then
      line=$(ss -tan "sport = :$port or dport = :$port" 2>/dev/null | tail -n +2 | tr '\n' ';')
      echo "$ts port=$port $line"
    else
      echo "$ts port=(pending)"
    fi
    sleep 1
  done
) > "$work/tcp.log" 2>&1 &

# milestone watcher
(
  tail -f -n 0 "$work/ux.log" 2>/dev/null | while read -r line; do
    case "$line" in
      *"loadURL called"*) echo "$(date +%H:%M:%S) MS loadURL" ;;
      *"Splash screen is ready"*) echo "$(date +%H:%M:%S) MS splash-ready" ;;
      *"Splash"*) echo "$(date +%H:%M:%S) MS splash-line" ;;
      *LOLSIGFAIL*) echo "$(date +%H:%M:%S) EVENT $(echo "$line" | cut -c1-90)" ;;
    esac
  done
) > "$work/milestones.log" 2>&1 &

# window tree + window-level captures at 50/120/200 s
for t in 50 120 200; do
  target=$((start + t))
  while [ "$(date +%s)" -lt "$target" ] && alive; do sleep 2; done
  DISPLAY=:1 xwininfo -root -tree 2>/dev/null > "$work/wintree-$t.txt"
  for wid in $(grep -a -o 'Riot Client[^"]*' -m3 /dev/null; true); do :; done
  # capture every mapped window whose name contains 'Riot Client' or 'Electron'
  for wid in $(DISPLAY=:1 xwininfo -root -tree 2>/dev/null | grep -a 'Riot Client\|index.html' | grep -oE '0x[0-9a-f]+' | head -4); do
    DISPLAY=:1 xwd -id "$wid" -silent -out "$work/win-$t-0x${wid#0x}.xwd" 2>/dev/null
  done
done

end=$((start + 260))
while [ "$(date +%s)" -lt "$end" ] && alive; do sleep 2; done
pkill -9 -x mldr 2>/dev/null; sleep 3
kill -KILL $lpid 2>/dev/null
pkill -9 -x mldr; pkill -9 -x darlingserver; pkill -9 -x launchd; pkill -9 -x darling
echo "=== milestones:"; cat "$work/milestones.log" 2>/dev/null | head -15
echo "=== tcp sample head/tail:"; head -8 "$work/tcp.log"; echo ...; tail -8 "$work/tcp.log"
echo "=== window captures:"; ls -la "$work"/*.xwd 2>/dev/null | awk '{print $5, $9}'
echo "=== wintree sample:"; grep -a 'Riot Client\|index.html' "$work/wintree-50.txt" 2>/dev/null | head -6
