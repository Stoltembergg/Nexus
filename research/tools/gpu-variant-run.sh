#!/bin/sh
# gpu-variant-run.sh LABEL [ENV=VALUE ...]  - relaunch a practice match with extra environment (e.g. RADV_DEBUG=nodcc),
# then run three stationary fight probes and print GPU ms/frame (game drm-engine-gfx share / fps).
cd "$(dirname "$0")/.."
label=$1; shift
for kv in "$@"; do export "$kv"; done
sh tools/baron-up.sh > /tmp/variant-$label-up.log 2>&1
g=$(for p in /proc/[0-9]*; do case "$(tr '\0' '\n' < $p/cmdline 2>/dev/null | head -1)" in */Game/LeagueOfLegends.app/Contents/MacOS/LeagueofLegends) echo ${p#/proc/};; esac; done 2>/dev/null | head -1)
i=0; until grep -q "game pid $g focused: limited" /tmp/ui-throttle.log 2>/dev/null || [ $i -gt 30 ]; do i=$((i+1)); sleep 5; done
echo "variant=$label env=$* game=$g radv=$(tr '\0' '\n' < /proc/$g/environ 2>/dev/null | grep -E '^RADV' | tr '\n' ' ')"
for n in 1 2 3; do sh tools/gpu-feed-probe.sh off 2>&1 | grep -v cmdline | tail -2 | tr '\n' ' ' | python3 -I -c "
import sys,re
s=sys.stdin.read(); g=re.search(r'gpu_gfx=(\d+)%',s); f=re.search(r\"'fps': ([\d.]+)\",s); p=re.search(r\"'p99_ms': ([\d.]+)\",s); m=re.search(r'main_run=(\d+)%',s)
print('  fps %s  p99 %s ms  gpu %s%%  main %s%%  => GPU %.1f ms/frame'%(f.group(1),p.group(1),g.group(1),m.group(1),int(g.group(1))*10/float(f.group(1))) if g and f else '  invalid: '+s[-120:])"; done
