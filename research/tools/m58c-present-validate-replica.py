#!/usr/bin/env python3
# darling-lol M58c: host-side replica of presentRemoteCAFrame:'s validation
# (X11Window.m) run repeatedly against the live slot.
import struct, os, time, sys, glob

paths = glob.glob(f"/dev/shm/darling-ca-frame-{os.getuid()}-*")
if not paths:
    sys.exit("no per-pid slots")
print(f"{len(paths)} publisher slot(s): {[p.rsplit('-',1)[1] for p in paths]}")
valid = 0
tried = 0
reasons = {}
lastSeq = None
deadline = time.time() + 12
while time.time() < deadline:
    tried += 1
    for path in paths:
        try:
            with open(path, "rb") as f:
                before = f.read(32)
            if len(before) != 32:
                reasons["short"] = reasons.get("short", 0) + 1
                continue
            magic, seq, w, h, bpr, pf, size = struct.unpack("<IIIIIIQ", before)
            if magic != 0x43414652: reasons["magic"] = reasons.get("magic", 0) + 1
            elif seq & 1: reasons["odd-seq"] = reasons.get("odd-seq", 0) + 1
            elif seq == lastSeq: reasons["same-seq"] = reasons.get("same-seq", 0) + 1
            elif w == 0 or h == 0: reasons["zero-size"] = reasons.get("zero-size", 0) + 1
            elif bpr < w * 4: reasons["bpr"] = reasons.get("bpr", 0) + 1
            elif size != bpr * h: reasons["size"] = reasons.get("size", 0) + 1
            else:
                with open(path, "rb") as f:
                    f.seek(32)
                    px = f.read(size)
                with open(path, "rb") as f:
                    after = f.read(32)
                aseq = struct.unpack("<II", after[:8])[1]
                if aseq != seq or aseq & 1:
                    reasons["torn"] = reasons.get("torn", 0) + 1
                else:
                    valid += 1
                    lastSeq = seq
                    nz = sum(1 for b in px[:3780*50] if b)
                    reasons[f"OK:{w}x{h}:{'pixels' if nz else 'BLACK'}"] = reasons.get(f"OK:{w}x{h}:{'pixels' if nz else 'BLACK'}", 0) + 1
        except FileNotFoundError:
            pass
    time.sleep(1/60)
print(f"tried={tried} valid={valid}")
for k, v in reasons.items():
    print(f"  {k}: {v}")
