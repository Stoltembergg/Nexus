#!/usr/bin/env python3
"""Watch mvg's lazy-import slot for _sysctlbyname in a live LeagueClient guest.

Purpose (M703): the LeagueClient crash jumps through mvg __la_symbol_ptr slot
0x111b5d8 which holds a poisoned value (SIGSEGV at 0xFFFFFFFFxxxxxxxx). This
probe waits for the mvg mapping, attaches gdb, snapshots the slot value as soon
as mvg is loaded, arms a hardware write watchpoint on it, then records every
writer (pc + rbp chain) and any subsequent SIGSEGV. Outcomes:

  * slot garbage at first snapshot        -> poisoned during load (dyld bind
                                             opcode processing for mvg or a
                                             pre-call mvg pass)
  * slot == stub_helper-ish, watchpoint
    fires later with writer in mvg       -> mvg's own code overwrites it
  * watchpoint writer in system dyld/libdyld -> runtime binder bug
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--timeout", type=int, default=420)
parser.add_argument("--slot", type=lambda x: int(x, 16), default=0x111b5d8,
                    help="mvg-relative __la_symbol_ptr offset for _sysctlbyname (hex)")
parser.add_argument("--out", default="/tmp/mvg-slot-watch.jsonl")
args = parser.parse_args()

root = Path(__file__).resolve().parent.parent
deadline = time.time() + args.timeout
out = Path(args.out)
out.write_text("")


def find_league_pid():
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.joinpath("exe").readlink().name != "mldr":
                continue
            text = entry.joinpath("maps").read_text()
        except OSError:
            continue
        if "LeagueClient.app/Contents/MacOS/LeagueClient" in text:
            return int(entry.name)
    return None


def mvg_mapping(pid):
    try:
        lines = Path(f"/proc/{pid}/maps").read_text().splitlines()
    except OSError:
        return None
    first = None
    end = 0
    for line in lines:
        if "mvg.framework" in line:
            fields = line.split()
            start, stop = (int(x, 16) for x in fields[0].split("-"))
            offset = int(fields[2], 16)
            if first is None or offset == 0:
                first = (start, offset)
            end = max(end, stop)
        if first is not None and "LeagueClient.app" in line and "MacOS/LeagueClient" not in line:
            continue
    if first is None:
        return None
    start, offset = first
    return {"base": start - offset, "span": end - start + offset}


pid = None
while time.time() < deadline and pid is None:
    pid = find_league_pid()
    if pid is None:
        time.sleep(0.4)
if pid is None:
    print("no LeagueClient guest appeared", file=sys.stderr)
    sys.exit(1)
print(f"league guest pid {pid}", flush=True)

mapping = None
while time.time() < deadline and mapping is None:
    mapping = mvg_mapping(pid)
    if mapping is None:
        time.sleep(0.05)
if mapping is None:
    print("mvg never mapped", file=sys.stderr)
    sys.exit(1)
base = mapping["base"]
slot_va = base + args.slot
print(f"mvg base {hex(base)} slot {hex(slot_va)}", flush=True)

params = {"base": base, "slot_va": slot_va, "span": mapping["span"],
          "pid": pid, "out": str(out)}

gdb_python = r"""
import json
import pathlib

params = json.loads(PAYLOAD)
base = params["base"]; slot_va = params["slot_va"]; span = params["span"]

records = []

def write_records():
    pathlib.Path(params["out"]).write_text(
        "\n".join(json.dumps(r) for r in records) + "\n")

def describe(pc):
    if base <= pc < base + span:
        return "mvg+" + hex(pc - base)
    return None

def read_slot():
    raw = gdb.selected_inferior().read_memory(slot_va, 8)
    return int.from_bytes(raw, "little")

def rchain(rbp, limit=10):
    frames = []
    address = rbp
    inferior = gdb.selected_inferior()
    while address and address % 8 == 0 and len(frames) < limit:
        try:
            raw = bytes(inferior.read_memory(address, 16))
        except Exception:
            break
        saved, ret = (int.from_bytes(raw[i*8:(i+1)*8], "little") for i in range(2))
        if saved <= address:
            break
        frames.append({"ret": hex(ret), "image": describe(ret)})
        address = saved
    return frames

gdb.execute("attach %d" % params["pid"], to_string=True)

try:
    snap = read_slot()
    records.append({"event": "attach_snapshot", "value": hex(snap)})
except Exception as exc:
    records.append({"event": "attach_snapshot_error", "error": str(exc)})
write_records()

gdb.execute("watch -l *(long*)%d" % slot_va, to_string=True)

gdb.execute("handle SIGSEGV stop nopass", to_string=True)
gdb.execute("handle SIGILL stop nopass", to_string=True)
gdb.execute("handle SIGTRAP stop nopass", to_string=True)

for i in range(16):
    try:
        gdb.execute("continue", to_string=True)
    except gdb.error:
        break
    inferior = gdb.selected_inferior()
    if not inferior.pid:
        break
    try:
        pc = int(gdb.parse_and_eval("$pc"))
    except Exception:
        break
    regs = {}
    for r in ("rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11"):
        try:
            regs[r] = hex(int(gdb.parse_and_eval("$" + r)))
        except Exception:
            pass
    try:
        rbp = int(gdb.parse_and_eval("$rbp"))
    except Exception:
        rbp = 0
    value = None
    try:
        value = read_slot()
    except Exception:
        pass
    try:
        inst = gdb.execute("x/i $pc", to_string=True).strip()
    except Exception:
        inst = ""
    records.append({
        "event": "stop", "index": i, "pc": hex(pc),
        "writer_image": describe(pc), "slot_value": hex(value) if value is not None else None,
        "rsi_plus_8": hex(int(gdb.parse_and_eval("$rsi")) + 8),
        "instruction": inst, "regs": regs, "chain": rchain(rbp),
    })
    write_records()

try:
    gdb.execute("detach", to_string=True)
except Exception:
    pass
write_records()
"""

script = (
    "set pagination off\nset confirm off\npy\n"
    + "PAYLOAD = '''" + json.dumps(params) + "'''\n"
    + gdb_python + "\nend\n"
)

with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as handle:
    handle.write(script)
    script_path = handle.name

try:
    subprocess.run(["gdb", "-batch", "-nx", "-x", script_path],
                   timeout=max(60, deadline - time.time() + 120))
except subprocess.TimeoutExpired:
    print("gdb timed out", file=sys.stderr)

print(out.read_text()[:6000])
