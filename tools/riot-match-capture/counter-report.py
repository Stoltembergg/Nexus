#!/usr/bin/env python3
"""Summarise a counter-match.py capture of the game's main thread.

Prints instructions per cycle and, per thousand instructions, branch mispredictions, L1 cache misses and TLB misses,
with an upper bound for the cycles lost to page walks: walks overlap with each other and with other misses, so
"30 cycles per walk, none overlapping" overstates the cost; a value near zero rules huge pages out as a lever. If the game's netstats.csv is given, the same is shown for the slowest and the fastest
quarter of its 10-second rows (rows are aligned from the start of both files).

Usage: counter-report.py build/logs/host-counters-<stamp>.jsonl [GameLogs/<date> directory] [skip_seconds=120]
"""
import csv
import glob
import json
import sys


def summary(label, rows):
    total = {}
    for row in rows:
        for key, value in row.items():
            if key != "t":
                total[key] = total.get(key, 0) + value
    instructions = total.get("instructions") or 1
    cycles = total.get("cycles") or 1
    per_k = lambda key: 1000 * total.get(key, 0) / instructions
    walks = total.get("itlb_walks", 0) + total.get("dtlb_walks", 0)
    print("%-16s IPC %.2f | per 1000 instructions: branch misses %.2f, L1i misses %.2f, L1d misses %.2f, "
          "iTLB L2 hits %.2f, iTLB walks %.3f, dTLB L2 hits %.2f, dTLB walks %.3f (4K %.3f) | page walks at most ~%.1f%% of cycles"
          % (label, total.get("instructions", 0) / cycles, per_k("branch_misses"), per_k("l1i_misses"),
             per_k("l1d_misses"), per_k("itlb_l1_miss_l2_hit"), per_k("itlb_walks"), per_k("dtlb_l1_miss_l2_hit"),
             per_k("dtlb_walks"), per_k("dtlb_walks_4k"), 100 * 30 * walks / cycles))


def main():
    rows = [json.loads(line) for line in open(sys.argv[1])]
    skip = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    summary("whole match", rows[skip:])
    if len(sys.argv) > 2 and sys.argv[2]:
        net = list(csv.DictReader(open(glob.glob(sys.argv[2] + "/*netstats.csv")[0])))
        slices = []
        for i, n in enumerate(net[:-1]):
            segment = rows[10 * i:10 * i + 10]
            if 10 * i >= skip and len(segment) == 10:
                slices.append((1 / float(n["game.frametime_average"]), segment))
        slices.sort(key=lambda s: s[0])
        quarter = max(1, len(slices) // 4)
        for label, group in (("slowest quarter", slices[:quarter]), ("fastest quarter", slices[-quarter:])):
            summary("%s %.0f fps" % (label, sum(f for f, _ in group) / len(group)), [r for _, s in group for r in s])


if __name__ == "__main__":
    main()
