#!/usr/bin/env python3
import collections
import struct
import sys

names = [
    "", "LOADED", "SET_VISIBLE", "SET_FRAME_SINK", "DRAW_AND_SWAP",
    "SCHEDULER_BEGIN_FRAME", "NATIVE_VISIBILITY", "RWHV_SHOW", "SUSPEND",
    "UNSUSPEND", "VIZ_SET_VISIBLE", "SCHEDULER_SET_VISIBLE",
    "ROOT_SET_VISIBLE", "UPDATE_LAYER_TREE", "GOT_LAYER_FRAME",
    "TIME_SOURCE_SET_ACTIVE", "TIME_SOURCE_TICK", "BEGIN_SOURCE_ADD",
    "BEGIN_SOURCE_TICK", "SET_NEEDS_ONE_FRAME",
    "ISSUE_TO_OBSERVER", "OBSERVER_ON_FRAME", "SCHEDULER_DERIVED_FRAME",
    "ARGS_FRAME_TIME", "ARGS_INTERVAL", "LAST_FRAME_TIME", "LAST_INTERVAL",
    "ARGS_FLAGS",
    "OBSERVER_VFN2", "OBSERVER_VFN3", "OBSERVER_VFN5",
]
data = open(sys.argv[1], "rb").read()
records = [struct.unpack_from("IIQ", data, offset)
           for offset in range(0, len(data) - 15, 16)]
counts = collections.Counter((pid, event) for pid, event, _ in records)
for (pid, event), count in sorted(counts.items()):
    values = [value for p, e, value in records if p == pid and e == event]
    shown = ",".join(hex(v) for v in values[:8])
    print(f"pid={pid} {names[event]} count={count} values={shown}")
