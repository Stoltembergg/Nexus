#!/usr/bin/env python3
"""Attach to the LeagueClientUx guest at birth and record who ends the process.

Stops on exit_group/exit syscalls and fatal signals; records code locations
(file + file offset) for the stopping thread only. No memory contents or
command-line arguments are captured.
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
parser.add_argument("--out", default="/tmp/league-ux-exit.jsonl")
parser.add_argument("--exclude-pid", type=int, action="append", default=[])
parser.add_argument("--faults-only", action="store_true")
parser.add_argument("--pid", type=int)
args = parser.parse_args()
deadline = time.time() + args.timeout


def find():
    if args.pid:
        return args.pid if Path(f"/proc/{args.pid}").exists() else None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.joinpath("exe").readlink().name != "mldr":
                continue
            if int(entry.name) not in args.exclude_pid and args.match in entry.joinpath("maps").read_text():
                return int(entry.name)
        except OSError:
            continue
    return None


pid = None
while time.time() < deadline and pid is None:
    pid = find()
    if pid is None:
        time.sleep(0.02)
if pid is None:
    sys.exit("no UX guest appeared")

GDB = r"""
import json, pathlib
out = pathlib.Path(OUT)
records = []

def regions():
    found = []
    for line in pathlib.Path("/proc/%d/maps" % PID).read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6:
            continue
        start, stop = (int(x, 16) for x in fields[0].split("-"))
        found.append((start, stop, int(fields[2], 16), fields[5]))
    return found

def resolve(pc, maps):
    for start, stop, offset, path in maps:
        if start <= pc < stop:
            return "%s+%#x" % (pathlib.Path(path).name, pc - start + offset)
    return "?%#x" % pc

def chain():
    maps = regions()
    pc = int(gdb.parse_and_eval("$pc")); rbp = int(gdb.parse_and_eval("$rbp")); rsp = int(gdb.parse_and_eval("$rsp"))
    frames = [resolve(pc, maps)]
    address = rbp
    while address and address % 8 == 0 and len(frames) < 24:
        try:
            raw = bytes(gdb.selected_inferior().read_memory(address, 16))
        except Exception:
            break
        saved = int.from_bytes(raw[:8], "little"); ret = int.from_bytes(raw[8:], "little")
        frames.append(resolve(ret, maps))
        if saved <= address:
            break
        address = saved
    window = []
    for step in range(96):
        try:
            value = int.from_bytes(bytes(gdb.selected_inferior().read_memory(rsp + step * 8, 8)), "little")
        except Exception:
            break
        for start, stop, offset, path in maps:
            if start <= value < stop and ".dylib" not in path and "/usr/lib" not in path and path.startswith("/") and "r-x" :
                name = pathlib.Path(path).name
                if name in ("LeagueClientUx", "Chromium Embedded Framework"):
                    window.append("%s+%#x" % (name, value - start + offset))
                break
    return frames, window[:30]

gdb.execute("attach %d" % PID, to_string=True)
records.append({"event": "attached"})
if not FAULTS_ONLY:
    gdb.execute("catch syscall exit_group", to_string=True)
    gdb.execute("catch syscall exit", to_string=True)
for name in ("SIGSEGV", "SIGILL", "SIGABRT", "SIGBUS", "SIGTRAP", "SIGFPE"):
    gdb.execute("handle %s stop nopass" % name, to_string=True)
for i in range(6):
    try:
        text = gdb.execute("continue", to_string=True)
    except gdb.error as error:
        records.append({"event": "continue_error", "text": str(error)[:200]})
        break
    if not gdb.selected_inferior().pid:
        records.append({"event": "exited", "text": text[-200:]})
        break
    try:
        frames, window = chain()
        thread = gdb.selected_thread()
        records.append({"event": "stop", "why": text.strip().splitlines()[-2:] if text else [],
                        "threadName": thread.name, "tid": thread.ptid[1],
                        "mainThread": thread.ptid[1] == PID,
                        "rdi": int(gdb.parse_and_eval("$rdi")) & 0xffffffff,
                        "frames": frames, "stackCode": window})
    except Exception as error:
        records.append({"event": "stop_error", "text": str(error)[:200]})
    out.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    if "exit_group" in text:
        break
out.write_text("\n".join(json.dumps(r) for r in records) + "\n")
try:
    gdb.execute("detach", to_string=True)
except Exception:
    pass
"""
with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as handle:
    handle.write("set pagination off\nset confirm off\npy\nPID = %d\nOUT = %r\nFAULTS_ONLY = %r\n%s\nend\n" % (pid, args.out, args.faults_only, GDB))
    script = handle.name
Path(args.out).write_text("")
print(f"ux guest pid {pid}", flush=True)
try:
    result = subprocess.run(["gdb", "-batch", "-nx", "-x", script], capture_output=True, text=True,
                            timeout=max(60, deadline - time.time()))
    print(result.stdout[-1500:], result.stderr[-800:])
except subprocess.TimeoutExpired:
    print("gdb timed out")
