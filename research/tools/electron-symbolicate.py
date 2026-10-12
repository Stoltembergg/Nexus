#!/usr/bin/env python3
"""Resolve x86_64 Electron VM offsets using an official symbols archive.

Check the printed MODULE identifier against llvm-dwarfdump --uuid first.
Darling map file offsets include the fat slice offset; subtract that offset
before passing addresses here. No process memory or application data is read.
"""
import argparse
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive")
parser.add_argument("offsets", nargs="+", type=lambda value: int(value, 0))
args = parser.parse_args()
matches = {}
with zipfile.ZipFile(args.archive) as archive:
    name = next(name for name in archive.namelist()
                if name.endswith("/Electron Framework.sym"))
    with archive.open(name) as symbols:
        print(symbols.readline().decode().strip())
        for line in symbols:
            if not line.startswith(b"FUNC "):
                continue
            fields = line.decode().strip().split()
            if fields[1] == "m":
                fields.pop(1)
            start, size = int(fields[1], 16), int(fields[2], 16)
            for offset in args.offsets:
                if start <= offset < start + size:
                    matches[offset] = (offset - start, " ".join(fields[4:]))
for offset in args.offsets:
    if offset in matches:
        delta, name = matches[offset]
        print(f"{offset:#x}: {name} + {delta:#x}")
    else:
        print(f"{offset:#x}: no FUNC record")
