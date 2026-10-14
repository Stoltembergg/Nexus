#!/usr/bin/env python3
"""Compare matches captured by sample-match.py, using the game's own 10-second FPS rows (netstats.csv).

For each match: harmonic-mean FPS, the worst 10-second row, the mean of the slowest quarter, and per frame the main
thread's CPU time, its waits on the Darling server (recvmsg on its RPC socket) and on futexes, and how often it
blocked. The first 7 rows (loading) and the last row are skipped.

Usage: compare-matches.py LABEL=build/logs/host-sample-<stamp>.jsonl:<GameLogs/<date> directory> ...
"""
import csv
import glob
import json
import statistics
import sys
from collections import Counter


def load(sample, logdir):
    rows = [json.loads(line) for line in open(sample)]
    pid = str(rows[0]["game"])
    rows = rows[1:]
    net = list(csv.DictReader(open(glob.glob(logdir + "/*netstats.csv")[0])))
    out = []
    for i, n in enumerate(net[:-1]):
        segment = rows[10 * i:10 * i + 10]
        if i < 7 or len(segment) < 10:
            continue
        fps = 1 / float(n["game.frametime_average"])
        frames = fps * 10
        calls, run, blocks = Counter(), 0, 0
        for r in segment:
            main = r["game"].get(pid, {})
            calls.update(main.get("syscall", {}))
            run += main.get("run_ns", 0)
            blocks += main.get("slices", 0)
        total = sum(calls.values()) or 1
        share = lambda prefix: sum(c for k, c in calls.items() if k.startswith(prefix)) / total * 10000 / frames
        out.append(dict(fps=fps, run=run / frames / 1e6, rpc=share("47 "), futex=share("202"), blocks=blocks / frames,
                        gpu=statistics.mean(r["gpu_busy"][0] for r in segment if r["gpu_busy"])))
    return out


def main():
    for argument in sys.argv[1:]:
        label, _, paths = argument.partition("=")
        sample, _, logdir = paths.partition(":")
        rows = load(sample, logdir)
        slow = sorted(rows, key=lambda d: d["fps"])[:max(1, len(rows) // 4)]
        mean = lambda key, group: statistics.mean(d[key] for d in group)
        print("%-28s rows %3d  avg %.1f fps  worst %.1f  slowest quarter %.1f | per frame: main CPU %.2f ms, "
              "server wait %.2f ms, futex %.2f ms, blocks %.1f | GPU %.0f%%"
              % (label, len(rows), len(rows) / sum(1 / d["fps"] for d in rows), slow[0]["fps"], mean("fps", slow),
                 mean("run", rows), mean("rpc", rows), mean("futex", rows), mean("blocks", rows), mean("gpu", rows)))


if __name__ == "__main__":
    main()
