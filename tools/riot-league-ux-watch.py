#!/usr/bin/env python3
"""Sample the LeagueClientUx guest: thread stacks at fixed delays, faults, exit.

Records code locations only (file + file offset), never memory contents or
command-line arguments.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--timeout", type=int, default=900)
parser.add_argument("--match", default="MacOS/LeagueClientUx\n")
parser.add_argument("--samples", default="5,20")
parser.add_argument("--out", default="/tmp/league-ux-watch.jsonl")
parser.add_argument("--pid", type=int)
args = parser.parse_args()
deadline = time.time() + args.timeout
out = Path(args.out)
out.write_text("")


def emit(record):
    with out.open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def find():
    if args.pid:
        return args.pid if alive(args.pid) else None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.joinpath("exe").readlink().name != "mldr":
                continue
            if args.match in entry.joinpath("maps").read_text():
                return int(entry.name)
        except OSError:
            continue
    return None


def regions(pid):
    found = []
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        start, stop = (int(x, 16) for x in fields[0].split("-"))
        found.append((start, stop, int(fields[2], 16), fields[5]))
    return found


def alive(pid):
    try:
        return Path(f"/proc/{pid}/status").read_text().split("State:")[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


GDB = r"""
import json
frames = {}
for thread in gdb.selected_inferior().threads():
    try:
        thread.switch()
        pc = int(gdb.parse_and_eval("$pc")); rbp = int(gdb.parse_and_eval("$rbp"))
    except Exception:
        continue
    chain = [pc]
    address = rbp
    while address and address % 8 == 0 and len(chain) < 18:
        try:
            raw = bytes(gdb.selected_inferior().read_memory(address, 16))
        except Exception:
            break
        saved = int.from_bytes(raw[:8], "little"); ret = int.from_bytes(raw[8:], "little")
        chain.append(ret)
        if saved <= address:
            break
        address = saved
    frames[str(thread.ptid[1])] = chain
print("UXFRAMES " + json.dumps(frames))
"""


def sample(pid, label):
    try:
        maps = regions(pid)
    except OSError:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as handle:
        handle.write("set pagination off\nset confirm off\nattach %d\npy\n%s\nend\ndetach\n" % (pid, GDB))
        script = handle.name
    try:
        result = subprocess.run(["gdb", "-batch", "-nx", "-x", script], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        emit({"event": "sample_timeout", "label": label})
        return
    for line in result.stdout.splitlines():
        if not line.startswith("UXFRAMES "):
            continue
        threads = {}
        for tid, chain in json.loads(line[9:]).items():
            resolved = []
            for pc in chain:
                for start, stop, offset, path in maps:
                    if start <= pc < stop:
                        resolved.append(f"{Path(path).name}+{pc - start + offset:#x}")
                        break
                else:
                    resolved.append(f"?{pc:#x}")
            threads[tid] = resolved
        emit({"event": "sample", "label": label, "threads": threads})


pid = None
while time.time() < deadline and pid is None:
    pid = find()
    if pid is None:
        time.sleep(0.2)
if pid is None:
    sys.exit("no UX guest appeared")
born = time.time()
emit({"event": "found", "pid": pid})
pending = sorted(float(x) for x in args.samples.split(","))
while time.time() < deadline:
    if not alive(pid):
        emit({"event": "gone", "after": round(time.time() - born, 2)})
        break
    if pending and time.time() - born >= pending[0]:
        sample(pid, pending.pop(0))
    try:
        emit_threads = len(list(Path(f"/proc/{pid}/task").iterdir()))
    except OSError:
        emit_threads = 0
    last = (round(time.time() - born, 1), emit_threads)
    time.sleep(0.25)
emit({"event": "end", "last": last})
