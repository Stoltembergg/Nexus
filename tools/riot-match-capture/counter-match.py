#!/usr/bin/env python3
"""Waits for the League game process, then counts hardware events on its main thread until it exits.

Runs build/riot-hw-counters (build it from hw-counters.cpp) in counting mode, user space only: no samples, no
instruction addresses, nothing read from or written to the game. Writes build/logs/host-counters-<stamp>.jsonl,
one line per second. Ask the person playing before running it on their match.

Usage: counter-match.py [--max-seconds N]
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
spec = importlib.util.spec_from_file_location("sample", HERE / "sample-match.py")
sample = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sample)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=7200)
    parser.add_argument("--max-seconds", type=int, default=3600)
    parser.add_argument("--pid", type=int, help="count this thread instead of the game's main thread (self-test)")
    arguments = parser.parse_args()
    deadline = time.monotonic() + arguments.wait_seconds
    pid = arguments.pid
    while pid is None:
        pid = sample.find("game")
        if pid is None:
            if time.monotonic() > deadline:
                print(json.dumps({"event": "no_game"}), flush=True)
                return 1
            time.sleep(2)
    out = ROOT / "build/logs" / ("host-counters-%s.jsonl" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.parent.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"event": "start", "game": pid, "log": str(out)}), flush=True)
    result = subprocess.run([str(ROOT / "build/riot-hw-counters"), str(pid), str(out), str(arguments.max_seconds)])
    print(json.dumps({"event": "end", "log": str(out), "exit": result.returncode}), flush=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
