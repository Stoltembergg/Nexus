#!/bin/sh
# Capture N whole frames with RenderDoc (default 6), each with a screenshot of the game window taken at the same moment.
# Needs a run started with CYCLE_RENDERDOC=1. Output: logs/burst-<time>/frame-<i>.rdc + frame-<i>.png
set -u
cd "$(dirname "$0")/.."
n=${1:-6}
out=logs/burst-$(date +%H%M%S)
mkdir -p "$out"
win=$(DISPLAY=:1 xwininfo -root -tree 2>/dev/null | grep '"League of Legends (TM) Client"' | awk '{print $1}' | head -1)
i=1
while [ "$i" -le "$n" ]; do
  before=$(wc -l < build/renderdoc/capture-status.log 2>/dev/null || echo 0)
  echo 0 > build/renderdoc/capture-request
  DISPLAY=:1 xwd -silent -id "$win" -out "$out/frame-$i.xwd"
  t=0
  while [ "$(wc -l < build/renderdoc/capture-status.log 2>/dev/null || echo 0)" -le "$before" ] && [ $t -lt 100 ]; do sleep 0.1; t=$((t + 1)); done
  newest=$(ls -t build/renderdoc/captures/*.rdc 2>/dev/null | head -1)
  [ -n "$newest" ] && mv "$newest" "$out/frame-$i.rdc"
  magick "$out/frame-$i.xwd" "$out/frame-$i.png" && rm -f "$out/frame-$i.xwd"
  i=$((i + 1))
done
echo "$out"
ls -l "$out" | awk 'NR>1{print $5, $9}'
