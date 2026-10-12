#!/usr/bin/env python3
# darling-lol M58c: inspect the host-visible CA frame slot written by
# publishRemoteIOSurface (QuartzCore) — header + how many pixels are non-zero.
import struct, sys, os

path = f"/dev/shm/darling-ca-frame-{os.getuid()}"
if not os.path.exists(path):
    sys.exit(f"no slot at {path}")

with open(path, "rb") as f:
    hdr = f.read(32)
    magic, seq, w, h, bpr, pf, size = struct.unpack("<IIIIIIQ", hdr)
    print(f"magic={magic:#x} seq={seq} {w}x{h} bpr={bpr} pf={pf:#x} size={size}")
    if magic != 0x43414652 or w == 0:
        sys.exit("slot empty/invalid")
    rows = 0
    nonzero_rows = 0
    total_nonzero = 0
    while rows < h and rows < 200:
        row = f.read(bpr)
        nz = sum(1 for b in row if b)
        total_nonzero += nz
        if nz:
            nonzero_rows += 1
        rows += 1
    print(f"first {rows} rows: {nonzero_rows} non-zero, {total_nonzero} non-zero bytes")
    if nonzero_rows > 10:
        print("PIXELS PRESENT — window should no longer be black")
    else:
        print("PIXELS STILL ZERO")
