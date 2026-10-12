#!/usr/bin/env python3
"""Capture only code locations at League startup faults, without a memory dump."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time

parser = argparse.ArgumentParser()
parser.add_argument("--image", choices=["league", "game", "trustd"], default="league")
parser.add_argument("--timeout", type=int, default=600)
parser.add_argument("--images-only", action="store_true")
parser.add_argument("--exclude-pid", type=int, action="append", default=[])
args = parser.parse_args()
deadline = time.monotonic() + args.timeout
needle = {
    "league": "/LeagueClient.app/Contents/MacOS/LeagueClient",
    "game": "/Game/LeagueofLegends.app/Contents/MacOS/LeagueofLegends",
    "trustd": "/usr/libexec/trustd",
}[args.image]
pid = None
while time.monotonic() < deadline and pid is None:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if int(entry.name) not in args.exclude_pid and entry.stat().st_uid == os.getuid() and needle in entry.joinpath("maps").read_text():
                pid = int(entry.name)
                break
        except OSError:
            pass
    if pid is None:
        time.sleep(.1 if args.image == "trustd" else 1)
if pid is None:
    raise SystemExit("Target process did not start within the observation window")
print(json.dumps({"target": args.image, "pid": pid, "observed": True}), flush=True)
try:
    regions = []
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) >= 6 and "x" in fields[1]:
            start, end = [int(x, 16) for x in fields[0].split("-")]
            regions.append({"start": start, "end": end, "offset": int(fields[2], 16),
                            "image": Path(fields[5]).name})
    Path(f"/tmp/{args.image}-startup-images.json").write_text(json.dumps(regions))
except OSError:
    pass
if args.images_only:
    raise SystemExit(0)
commands = r'''
set pagination off
set confirm off
set print frame-arguments none
set print entry-values no
set print thread-events off
handle SIGPIPE SIGUSR1 SIGUSR2 SIGALRM SIGCHLD SIG32 SIG33 SIG34 SIG35 SIG36 SIG37 SIG38 SIG39 SIG40 SIG41 SIG42 SIG43 SIG44 SIG45 SIG46 SIG47 SIG48 SIG49 SIG50 SIG51 SIG52 SIG53 SIG54 SIG55 SIG56 SIG57 SIG58 SIG59 SIG60 SIG61 SIG62 SIG63 SIG64 nostop print pass
handle SIGSEGV stop print pass
handle SIGABRT stop print pass
handle SIGILL stop print pass
handle SIGBUS stop print pass
handle SIGFPE stop print pass
python
import gdb, json, re
from pathlib import Path
gdb.execute("attach TARGET_PID", to_string=True)
out = Path("/tmp/league-startup-faults.jsonl").open("a")
def locations():
    regions = []
    for line in Path("/proc/TARGET_PID/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) < 6 or "x" not in fields[1]: continue
        start, end = [int(x,16) for x in fields[0].split("-")]
        regions.append((start, end, int(fields[2],16), Path(fields[5]).name))
    def describe(pc):
        for start,end,offset,name in regions:
            if start <= pc < end: return {"image":name,"offset":hex(pc-start+offset)}
        return {"unmappedPc":hex(pc)}
    return describe
try:
    for number in range(24):
        gdb.execute("continue", to_string=True)
        if not gdb.selected_inferior().pid: break
        describe = locations()
        pc = int(gdb.parse_and_eval("$pc"))
        record = {"pid": TARGET_PID, "fault":number,"thread":gdb.selected_thread().name,"location":describe(pc)}
        try: record["faultAddress"] = hex(int(gdb.parse_and_eval("$_siginfo._sifields._sigfault.si_addr")))
        except Exception: pass
        for register in ("rax","rbx","rcx","rdx","rdi","rsi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"):
            try: record[register] = hex(int(gdb.parse_and_eval("$"+register)))
            except Exception: pass
        try:
            # darling-lol: guest images have no CFI for gdb; walk the saved-rbp chain
            # directly like the M638 stack prober did.
            chain = []
            anchor = int(gdb.parse_and_eval("$rbp"))
            inferior = gdb.selected_inferior()
            mem = lambda address: int.from_bytes(inferior.read_memory(address, 8), "little")
            address = anchor
            for step in range(24):
                if address == 0 or address % 8: break
                saved, ret = mem(address), mem(address + 8)
                chain.append(describe(ret))
                if saved <= address: break
                address = saved
            record["fpChain"] = chain
        except Exception: pass
        try:
            # darling-lol: raw stack window above rsp, decode code pointers.
            window = []
            rsp = int(gdb.parse_and_eval("$rsp"))
            for step in range(80):
                qword = mem(rsp + step * 8)
                image = describe(qword)
                if isinstance(image, dict) and "image" in image and image["image"] not in ("[vsyscall]",):
                    window.append(image)
            record["stackWindow"] = window[:24]
        except Exception: pass
        # Commit the exact signal location before attempting any unwinding.
        out.write(json.dumps(record)+"\n"); out.flush()
        frames = []; frame = gdb.newest_frame()
        for n in range(16):
            if frame is None: break
            try: frames.append(describe(frame.pc()))
            except Exception: break
            try: frame = frame.older()
            except Exception: break
        record["frames"] = frames
        try: record["instruction"] = gdb.execute("x/i $pc", to_string=True).strip()
        except Exception: pass
        out.write(json.dumps(record)+"\n"); out.flush()
except Exception as error:
    out.write(json.dumps({"observationEnded":True,"errorClass":type(error).__name__,"reason":str(error)[:160]})+"\n"); out.flush()
finally:
    if gdb.selected_inferior().pid:
        try: gdb.execute("detach", to_string=True)
        except Exception: pass
    out.close()
end
'''.replace("TARGET_PID", str(pid)).replace("league-startup-faults", args.image + "-startup-faults")
with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as script:
    script.write(commands)
    script_path = script.name
try:
    result = subprocess.run(["gdb", "-batch", "-nx", "-x", script_path],
                            capture_output=True, text=True, timeout=300)
    diagnostic = result.stdout + result.stderr
    print(json.dumps({"debuggerExit": result.returncode,
                      "processGone": "No such process" in diagnostic,
                      "permissionError": "Operation not permitted" in diagnostic,
                      "pythonError": "Python Exception" in diagnostic or "Traceback" in diagnostic,
                      "inferiorExited": "exited" in diagnostic,
                      "debuggerSignals": sorted(set(__import__("re").findall(r"SIG[A-Z0-9]+", diagnostic))),
                      "diagnosticBytes":len(diagnostic)}), flush=True)
except subprocess.TimeoutExpired:
    print(json.dumps({"observationTimeout": True}), flush=True)
finally:
    Path(script_path).unlink(missing_ok=True)
