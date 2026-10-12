#!/bin/sh
# gpu-feed-probe.sh MODE   (MODE: off|on = deferred encoding) - one stationary workload with GPU-share / main-thread probes.
cd "$(dirname "$0")/.."
unset ELECTRON_RUN_AS_NODE
g=$(for p in /proc/[0-9]*; do case "$(tr '\0' '\n' < $p/cmdline 2>/dev/null | head -1)" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) echo ${p#/proc/};; esac; done | head -1)
[ -n "$g" ] || { echo "no game"; exit 1; }
if [ "$1" = on ]; then timeout 15 darling shell touch /tmp/metal-async-encode >/dev/null 2>&1; else timeout 15 darling shell rm -f /tmp/metal-async-encode >/dev/null 2>&1; fi
timeout 15 darling shell touch /tmp/metal-frame-interval-repeat >/dev/null 2>&1
hyprctl eval 'hl.dispatch(hl.dsp.focus({window="class:^(LeagueofLegends)$"}))' >/dev/null 2>&1; sleep 2
gpu(){ cat /proc/$g/fdinfo/* 2>/dev/null | awk '/^drm-client-id/{id=$2} /^drm-engine-gfx/{ if(!(id in s)){s[id]=1; t+=$2} } END{print t+0}'; }
python3 -I tools/baron-workload.py --stationary --seconds 18 > /tmp/probe-$1.json 2>/tmp/probe-$1.err &
w=$!
sleep 4
g0=$(gpu); read r1 q1 s1 < /proc/$g/task/$g/schedstat; t0=$(date +%s%N)
sleep 10
g1=$(gpu); read r2 q2 s2 < /proc/$g/task/$g/schedstat; t1=$(date +%s%N)
wait $w
dt=$((t1-t0))
echo "mode=$1 gpu_gfx=$(( (g1-g0)*100/dt ))% main_run=$(( (r2-r1)*100/dt ))% main_runq=$(( (q2-q1)*100/dt ))%"
python3 -I -c "
import json
s=open('/tmp/probe-$1.json').read(); d=json.loads(s[s.find('{'):]); print({k:d[k] for k in ('fps','p50_ms','p95_ms','p99_ms','worst_ms','frames')})" 2>/dev/null || tail -2 /tmp/probe-$1.err
