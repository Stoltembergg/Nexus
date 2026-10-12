#!/usr/bin/env bash
# darling-lol M58ac: repeated loop-latency sampling across configs and runs.
#
# Each run boots the UX, takes 8 loop samples (~3 s apart) via
# tools/m58ac-loop-samples.py, and records the host load and the app's
# "Splash screen is ready to show" milestone so slow phases can be
# correlated. Configs: baseline, OTEL_SDK_DISABLED, software compositing.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT=/tmp/opencode/m58ac; rm -rf "$OUT"; mkdir -p "$OUT"
UXRUN='@DPREFIX@/Applications/Riot Client.app/Contents/Frameworks/Riot Client.app/Contents/MacOS/Riot Client'
ARGS=(--app-port=39061 --remoting-auth-token=DARLINGTEST --app-pid=1 --inspect=9229
      --enableHardwareAcceleration
      '--log-dir=@GUEST_HOME@/Library/Logs/Riot Games/Riot Client'
      '--app-root=/Applications/Riot Client.app')
SWARGS=("${ARGS[@]}" --disable-gpu-compositing)

run_one() {
  local tag="$1"; shift
  /tmp/opencode/cleandarling.sh >/dev/null 2>&1
  echo "=== $tag  $(date -Is)  load=$(cut -d' ' -f1 /proc/loadavg)" | tee -a "$OUT/summary.txt"
  setsid "$@" > "$OUT/$tag-ux.log" 2>&1 &
  local lpid=$!
  sleep 92
  python3 "$HERE/m58ac-loop-samples.py" -n 8 -i 3 --tag "$tag" \
      > "$OUT/$tag.samples" 2>&1
  # summarise this run
  local sl slow
  sl=$(grep -aoE 't0_ms=[0-9]+' "$OUT/$tag.samples" | cut -d= -f2 | tr '\n' ' ')
  slow=$(echo "$sl" | tr ' ' '\n' | awk '$1>1000' | wc -l)
  local splash
  splash=$(grep -a 'Splash screen is ready' "$OUT/$tag-ux.log" | tail -1 | grep -aoE '^[0-9:.]+' | head -1)
  echo "  t0_ms=[$sl] slow(>1s)=$slow/8 splash_ready=$splash  load_after=$(cut -d' ' -f1 /proc/loadavg)" \
      | tee -a "$OUT/summary.txt"
  kill -9 $lpid 2>/dev/null
  pkill -9 -x mldr 2>/dev/null; pkill -9 -x darlingserver 2>/dev/null
  pkill -9 -x launchd 2>/dev/null; pkill -9 -x darling 2>/dev/null
  /tmp/opencode/cleandarling.sh >/dev/null 2>&1
}

for i in 1 2; do
  run_one "base-r$i"   env DISPLAY=:1 darling "$UXRUN" "${ARGS[@]}"
  run_one "otlpoff-r$i" env DISPLAY=:1 OTEL_SDK_DISABLED=true darling "$UXRUN" "${ARGS[@]}"
  run_one "swcomp-r$i" env DISPLAY=:1 darling "$UXRUN" "${SWARGS[@]}"
done
echo "ALL DONE"
