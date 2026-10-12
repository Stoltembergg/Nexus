#!/usr/bin/env python3
"""Guarded Riot Electron 22 ScriptStreamer CHECK workaround (M58h).

The app's macOS Chromium CHECK traps when a Darling mojo wait returns its
unexpected result. This changes only the six-byte branch that enters the trap.
Use --revert to restore the original guarded bytes.
"""
import argparse
import os
from pathlib import Path

TARGET = (Path.home() / '.darling/Applications/Riot Client.app/Contents/Frameworks/'
          'Riot Client.app/Contents/Frameworks/Electron Framework.framework/'
          'Versions/A/Electron Framework')
OFFSET = 0x526108B
ORIGINAL = bytes.fromhex('0f 85 da 00 00 00')
PATCHED = bytes.fromhex('90 90 90 90 90 90')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revert', action='store_true')
    args = ap.parse_args()
    before, after = (PATCHED, ORIGINAL) if args.revert else (ORIGINAL, PATCHED)
    stat = TARGET.stat()
    with TARGET.open('r+b') as f:
        f.seek(OFFSET)
        actual = f.read(len(before))
        if actual == after:
            print('already', 'reverted' if args.revert else 'patched')
            return
        if actual != before:
            raise SystemExit(f'unexpected bytes at 0x{OFFSET:x}: {actual.hex(" ")}')
        f.seek(OFFSET)
        f.write(after)
        f.flush()
    os.utime(TARGET, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    print('reverted' if args.revert else 'patched', TARGET)


if __name__ == '__main__':
    main()
