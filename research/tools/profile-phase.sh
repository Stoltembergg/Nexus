#!/bin/sh
# Profile the running game for N seconds (default 20) and print the hottest inclusive functions of its main thread.
# Usage: sh tools/profile-phase.sh <label> [seconds]      Output: logs/phase-<label>/
# User-space sampling only (perf, no ptrace); Mach-O frames resolved by tools/symbolize-macho-perf.py.
set -eu
cd "$(dirname "$0")/.."
label=${1:?label}; secs=${2:-20}
out=logs/phase-$label; mkdir -p "$out"
python3 -I tools/capture-game-perf.py --seconds "$secs" --out "$out/capture" --top 1 > "$out/capture.txt" 2>&1 || { cat "$out/capture.txt"; exit 1; }
pid=$(sed -n 's/^game pid \([0-9]*\),.*/\1/p' "$out/capture.txt")
cp "/proc/$pid/maps" "$out/maps.txt"
python3 -I tools/symbolize-macho-perf.py "$out/capture/game-main.data" "$out/maps.txt" --out "$out/symbols.json" > "$out/symbolize.txt" 2>&1 || { tail -5 "$out/symbolize.txt"; exit 1; }
python3 -I - "$out" <<'PY'
import json, sys
out = sys.argv[1]
d = json.load(open(out + '/symbols.json'))
summ = json.load(open(out + '/capture/summary.json'))
print('clock', summ.get('game_clock_before'), '->', summ.get('game_clock_after'), 'wall', summ.get('wall_s'))
k = max(d, key=lambda t: d[t]['total_weight'])
t = d[k]
print('thread', k, 'samples', t['samples'])
print('-- by library'); [print('%6.2f%% %s' % (e['pct'], e['symbol'])) for e in t['dso'][:10]]
print('-- inclusive'); [print('%6.2f%% %s' % (e['pct'], e['symbol'])) for e in t['inclusive'][:34]]
PY
