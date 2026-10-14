#!/usr/bin/env python3
"""Waits for the League game process, then runs the instruction-address sampler
on it while recording its memory-map layout and per-thread CPU counters from
/proc. Stops when the game exits. Attaches no debugger and writes nothing to
the game."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location("sample", HERE / "sample-match.py")
sample = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sample)


def threads(pid):
    rows = {}
    try:
        tids = os.listdir("/proc/%d/task" % pid)
    except OSError:
        return None
    for tid in tids:
        base = "/proc/%d/task/%s/" % (pid, tid)
        stat = sample.read(base + "stat").rsplit(")", 1)
        sched = sample.read(base + "schedstat").split()
        if len(stat) != 2 or len(sched) != 3:
            continue
        fields = stat[1].split()
        rows[tid] = [sample.read(base + "comm"), int(fields[11]), int(fields[12]), int(sched[0]), int(sched[1]), int(sched[2])]
    return rows


def main():
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    limit = sys.argv[2] if len(sys.argv) > 2 else "3600"
    deadline = time.monotonic() + 6000
    while pid is None:
        pid = sample.find("game")
        if pid is None:
            if time.monotonic() > deadline:
                print(json.dumps({"event": "no_game"}), flush=True)
                return 1
            time.sleep(2)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prefix = ROOT / "build/logs" / ("host-profile-" + stamp)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    profiler = subprocess.Popen([str(ROOT / "build/riot-ip-profiler"), str(pid), str(prefix) + ".samples", limit])
    print(json.dumps({"event": "start", "prefix": str(prefix), "game": pid, "hz": os.sysconf("SC_CLK_TCK")}), flush=True)
    last_maps = None
    with open(str(prefix) + ".threads.jsonl", "w") as counters, open(str(prefix) + ".maps.jsonl", "w") as maps:
        second = 0
        while profiler.poll() is None:
            begin = time.monotonic()
            rows = threads(pid)
            if rows:
                counters.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "mono_ns": time.clock_gettime_ns(time.CLOCK_MONOTONIC), "threads": rows}) + "\n")
                counters.flush()
            if second % 15 == 0:
                text = sample.read("/proc/%d/maps" % pid)
                if text and text != last_maps:
                    maps.write(json.dumps({"mono_ns": time.clock_gettime_ns(time.CLOCK_MONOTONIC), "maps": text}) + "\n")
                    maps.flush()
                    last_maps = text
            second += 1
            time.sleep(max(0, 1 - (time.monotonic() - begin)))
    print(json.dumps({"event": "end", "prefix": str(prefix), "profiler_exit": profiler.returncode}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
