#!/usr/bin/env python3
# darling-lol M58e: symbolize a LOLSIGFAIL line against /proc/<mldr>/maps
# snapshots taken while the process was alive (host addresses).
#   m58e-symbolize.py <mapsfile-or-dir> <lolsig line | electron.log>
import glob, os, re, sys

def load_maps(path):
    segs = []
    with open(path) as f:
        for line in f:
            m = re.match(r'([0-9a-f]+)-([0-9a-f]+) .* (\S+)$', line.rstrip())
            if m:
                segs.append((int(m.group(1), 16), int(m.group(2), 16), m.group(3)))
    return segs

def find(segs, addr):
    for lo, hi, path in segs:
        if lo <= addr < hi:
            return f"{path}+{addr-lo:#x}"
    return None

maps_arg = sys.argv[1]
log_arg = sys.argv[2]
if os.path.isdir(maps_arg):
    samples = sorted(glob.glob(os.path.join(maps_arg, '*')), key=os.path.getmtime)
else:
    samples = [maps_arg]
print(f"{len(samples)} maps sample(s)")

text = open(log_arg, errors='ignore').read()
for line in text.splitlines():
    if 'LOLSIGFAIL' in line:
        raw = dict(re.findall(r'(\w+)=0x([0-9a-fA-F]+)', line))
        print(line[:160])
        keys = ('rip', 'ret0', 'ret1')
    elif 'LOLSIGFRAME' in line:
        flash = re.match(r'LOLSIGFRAME(\d+) rbp=0x([0-9a-fA-F]+) ret=0x([0-9a-fA-F]+)', line)
        if not flash:
            continue
        raw = {'rbp': flash.group(2), 'ret': flash.group(3)}
        print(line)
        keys = ('ret',)
    else:
        continue
    for key in keys:
        if key not in raw:
            continue
        addr = int(raw[key], 16)
        hit = None
        for path in samples:
            try:
                hit = find(load_maps(path), addr)
            except OSError:
                continue
            if hit:
                print(f"  {key}=0x{raw[key]} -> {path.rsplit('/',1)[1]}: {hit}")
                break
        if hit is None:
            print(f"  {key}=0x{raw[key]} -> None")
