#!/bin/sh
# interleaved A/B of lazy render-pass begin (guest flag /tmp/metal-no-lazy-pass): ON, OFF; each session: away x2, hover all-chain, hover chain-skipped
cd "$(dirname "$0")/.."
: > /tmp/lazy-ab.out
g() { timeout 60 darling shell sh -c "$1" >/dev/null 2>&1; }
run() {
  python3 -I tools/baron-workload.py --seconds 12 $2 2>&1 | python3 -c "
import sys,json
t=sys.stdin.read()
try:
    d=json.loads(t[t.index('{'):t.rindex('}')+1]); print('fps %.1f p50 %.1f p99 %.1f HP %s->%s' % (d['fps'],d['p50_ms'],d['p99_ms'],d.get('baron_hp_bar_px_start'),d.get('baron_hp_bar_px_end')))
except Exception: print('no result')"
}
session() {
  label=$1
  sh tools/baron-up.sh > /tmp/lazy-ab-up-$label.log 2>&1
  hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 1
  g 'touch /tmp/metal-frame-interval-repeat; rm -f /tmp/metal-outline-pairs /tmp/metal-outline-pairs2'; sleep 2
  hyprctl eval 'hl.dispatch(hl.dsp.cursor.move({x=1500,y=950}))' >/dev/null 2>&1
  run x --idle >/dev/null   # first run after a restart is unreliable
  echo "$label away:        $(run x --idle)" >> /tmp/lazy-ab.out
  echo "$label away:        $(run x --idle)" >> /tmp/lazy-ab.out
  echo "$label hover K1=0 K2=all: $(run x --autoattack)" >> /tmp/lazy-ab.out
  echo "$label hover K1=0 K2=all: $(run x --autoattack)" >> /tmp/lazy-ab.out
  g 'echo 0 > /tmp/metal-outline-pairs2'; sleep 2
  echo "$label hover K1=0 K2=0:   $(run x --autoattack)" >> /tmp/lazy-ab.out
  echo "$label hover K1=0 K2=0:   $(run x --autoattack)" >> /tmp/lazy-ab.out
  echo "$label tctl $(sensors | grep Tctl | tr -s ' ' | cut -d' ' -f2)" >> /tmp/lazy-ab.out
}
CYCLE_NO_LAZY_PASS=0 session lazy-ON-a
CYCLE_NO_LAZY_PASS=1 session lazy-OFF-a
CYCLE_NO_LAZY_PASS=0 session lazy-ON-b
CYCLE_NO_LAZY_PASS=1 session lazy-OFF-b
echo done >> /tmp/lazy-ab.out
