#!/bin/sh
# A/B/A of the ordered submit worker with the Baron workload: 4 runs per session, results in /tmp/submit-ab.out
cd "$(dirname "$0")/.."
: > /tmp/submit-ab.out
run_session() {
  label=$1
  rm -f "$HOME/.darling/tmp/metal-no-submit-thread"
  sh tools/baron-up.sh > /tmp/submit-ab-up-$label.log 2>&1
  cp /tmp/profile-cycle.log /tmp/submit-ab-cycle-$label.log 2>/dev/null
  for i in 1 2 3 4; do
    r=$(python3 -I tools/baron-workload.py --seconds 20 2>&1 | python3 -c "
import sys,json
t=sys.stdin.read()
try:
    d=json.loads(t[t.index('{'):t.rindex('}')+1]); print('fps %.1f mean %.1f p50 %.1f p99 %.1f' % (d['fps'],d['mean_ms'],d['p50_ms'],d['p99_ms']))
except Exception: print('no result')")
    echo "$label run$i: $r" >> /tmp/submit-ab.out
  done
}
CYCLE_NO_SUBMIT_THREAD=0 run_session "worker-ON-a"
CYCLE_NO_SUBMIT_THREAD=1 run_session "worker-OFF-a"
CYCLE_NO_SUBMIT_THREAD=0 run_session "worker-ON-b"
CYCLE_NO_SUBMIT_THREAD=1 run_session "worker-OFF-b"
echo done >> /tmp/submit-ab.out
