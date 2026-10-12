#!/bin/sh
# idle-at-Baron A/B of the buffer pool: ON, then OFF; results in /tmp/pool-ab.out
cd "$(dirname "$0")/.."
: > /tmp/pool-ab.out
session() {
  label=$1
  sh tools/baron-up.sh > /tmp/pool-ab-up-$label.log 2>&1
  for i in 1 2 3; do
    r=$(python3 -I tools/baron-workload.py --seconds 20 --idle 2>&1 | python3 -c "
import sys,json
t=sys.stdin.read()
try:
    d=json.loads(t[t.index('{'):t.rindex('}')+1]); print('fps %.1f p50 %.1f p95 %.1f p99 %.1f' % (d['fps'],d['p50_ms'],d['p95_ms'],d['p99_ms']))
except Exception: print('no result')")
    echo "$label idle$i: $r tctl $(sensors | grep Tctl | tr -s ' ' | cut -d' ' -f2)" >> /tmp/pool-ab.out
  done
}
CYCLE_NO_POOL=0 session pool-ON
CYCLE_NO_POOL=1 session pool-OFF
echo done >> /tmp/pool-ab.out
