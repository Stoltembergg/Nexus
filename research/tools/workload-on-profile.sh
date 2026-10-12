#!/bin/sh
# Wait for a new `sudo sh tools/true-profile.sh` capture to start, then run the Baron workload during its recording window.
cd "$(dirname "$0")/.."
before=$(ls -d logs/true-profile-* 2>/dev/null | wc -l)
i=0
while [ "$(ls -d logs/true-profile-* 2>/dev/null | wc -l)" -le "$before" ] && [ $i -lt 600 ]; do i=$((i+1)); sleep 1; done
sleep 10.5
python3 -I tools/baron-workload.py --seconds "${1:-34}"
