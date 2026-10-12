#!/bin/sh
# Unattended frame-time benchmark: restart the runtime with passive recorders, wait for the match and the 90 s capture
# warm-up, run the automated camera pan (tools/measure-repeatable-camera.py) and analyze the renderer's own
# presentation timestamps that fall inside the test window.
# Usage: sh tools/bench-camera.sh <label> [seconds=60] [--no-restart]     Output: logs/bench-<label>/
# Takes over keyboard input to the game window and hides the League client windows for the duration.
set -u
cd "$(dirname "$0")/.."
label=${1:?label}; secs=${2:-60}; restart=1
[ "${3:-}" = "--no-restart" ] && restart=0
out=logs/bench-$label
[ ! -e "$out" ] || { echo "$out exists" >&2; exit 1; }
mkdir -p "$out"
unset ELECTRON_RUN_AS_NODE VK_DRIVER_FILES
# The client UI processes burn ~1.7 cores behind the game and eat the shared power budget: measure with them paused, as in play.
throttle_running=0
for p in $(pgrep -x python3); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q 'game-ui-throttle' && throttle_running=1; done
[ $throttle_running = 1 ] || { setsid nohup python3 -I tools/game-ui-throttle.py > /tmp/game-ui-throttle.log 2>&1 < /dev/null & }
if [ $restart = 1 ]; then
  rm -f /tmp/dserver-call-stats.log "$HOME"/.darling/tmp/metal-present-intervals*.csv
  CYCLE_SERVER_STATS=1 CYCLE_FRAME_INTERVALS=1 sh tools/profile-cycle.sh > "$out/cycle.log" 2>&1 < /dev/null &
fi
# wait for a live match clock, then until the capture has had its 90 s warm-up
i=0; start=""
while [ $i -lt 400 ]; do
  t=$(curl -sk -m 3 https://127.0.0.1:2999/liveclientdata/gamestats 2>/dev/null | grep -o '"gameTime": *[0-9]*' | grep -o '[0-9]*$')
  [ -n "$t" ] && { start=$(date +%s); break; }
  i=$((i + 1)); sleep 3
done
[ -n "$start" ] || { echo "no match" >&2; exit 1; }
[ $restart = 1 ] && { now=$(date +%s); wait=$((start + 100 - now)); [ $wait -gt 0 ] && sleep $wait; }
python3 -I tools/measure-repeatable-camera.py --out "$out/camera" --seconds "$secs" --min-clock 100 > "$out/camera-output.txt" 2>&1
sleep 2
cp "$HOME"/.darling/tmp/metal-present-intervals*.csv "$out"/ 2>/dev/null
cp /tmp/dserver-call-stats.log "$out"/ 2>/dev/null
python3 -I - "$out" <<'PY'
import csv, glob, json, math, statistics, sys
out = sys.argv[1]
s = json.load(open(out + '/camera/summary.json'))
t0, t1 = int(s['before']['monotonic_s'] * 1e9), int(s['after']['monotonic_s'] * 1e9)
q = []
for f in glob.glob(out + '/metal-present-intervals*.csv'):
    for r in csv.DictReader(open(f)):
        v = int(r['queued_ns'])
        if t0 <= v <= t1: q.append(v)
q.sort()
iv = sorted((b - a) / 1e6 for a, b in zip(q, q[1:]) if b - a < 200e6)
if len(iv) < 50:
    print('too few presents in window:', len(iv)); sys.exit(1)
p = lambda x: iv[min(len(iv) - 1, math.ceil(len(iv) * x) - 1)]
res = dict(n=len(iv), mean_ms=statistics.mean(iv), p50_ms=p(.5), p90_ms=p(.9), p99_ms=p(.99), max_ms=iv[-1], fps=1000 / statistics.mean(iv),
           x11_median_ms=s['median_ms'], x11_p99_ms=s['p99_ms'], target_met=p(.99) < 11.111)
json.dump(res, open(out + '/result.json', 'w'), indent=1)
print('PRESENT intervals in window: n=%d mean=%.2f ms (%.1f fps) p50=%.2f p90=%.2f p99=%.2f max=%.2f | X11 median %.2f p99 %.2f | p99<11.1ms: %s' % (
    res['n'], res['mean_ms'], res['fps'], res['p50_ms'], res['p90_ms'], res['p99_ms'], res['max_ms'], res['x11_median_ms'], res['x11_p99_ms'], res['target_met']))
PY
