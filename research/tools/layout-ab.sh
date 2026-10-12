#!/bin/sh
# interleaved A/B of render-target layouts (guest flag /tmp/metal-opt-layouts): ON, OFF, ON, OFF; 3 auto-attack runs + 2 fight runs each
cd "$(dirname "$0")/.."
: > /tmp/layout-ab.out
session() {
  label=$1
  sh tools/baron-up.sh > /tmp/layout-ab-up-$label.log 2>&1
  timeout 90 darling shell sh -c 'touch /tmp/metal-frame-interval-repeat' >/dev/null 2>&1
  for mode in "--autoattack" "--autoattack" "--autoattack" "" ""; do
    r=$(python3 -I tools/baron-workload.py --seconds 15 $mode 2>&1 | python3 -c "
import sys,json
t=sys.stdin.read()
try:
    d=json.loads(t[t.index('{'):t.rindex('}')+1]); print('fps %.1f p50 %.1f p95 %.1f p99 %.1f baronHP %s->%s' % (d['fps'],d['p50_ms'],d['p95_ms'],d['p99_ms'],d.get('baron_hp_bar_px_start'),d.get('baron_hp_bar_px_end')))
except Exception: print('no result')")
    echo "$label ${mode:---fight}: $r tctl $(sensors | grep Tctl | tr -s ' ' | cut -d' ' -f2)" >> /tmp/layout-ab.out
  done
}
CYCLE_OPT_LAYOUTS=1 session layouts-ON-a
CYCLE_OPT_LAYOUTS=0 session layouts-OFF-a
CYCLE_OPT_LAYOUTS=1 session layouts-ON-b
CYCLE_OPT_LAYOUTS=0 session layouts-OFF-b
echo done >> /tmp/layout-ab.out
