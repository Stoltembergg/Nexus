#!/usr/bin/env python3
"""Guarded Electron 22.3.27 NativeWindowMac::IsVisible correction.

The original method rejects NSWindowOcclusionStateVisible (2). Reverse that
single condition so the normal visible/not-minimized checks can succeed.
Source: electron/electron v22.3.27 shell/browser/native_window_mac.mm:520.
Run after stopping Darling. --revert restores only this change.
"""
import argparse
import os
from pathlib import Path
import struct

TARGET = (Path.home() / '.darling/Applications/Riot Client.app/Contents/Frameworks/'
          'Riot Client.app/Contents/Frameworks/Electron Framework.framework/'
          'Versions/A/Electron Framework')
FUNCTION_VA = 0x531190
BRANCH_INDEX = 0x41
ORIGINAL = bytes.fromhex(
    '554889e54157415653504889fb488bbf88020000488b353d828c08'
    '4c8b3da60e2b0841ffd74989c6488bbb88020000488b352a828c08'
    '41ffd789c131c04983fe02740e84c9740a4889dfe8810400003401'
    '4883c4085b415e415f5dc3')
PATCHED = ORIGINAL[:BRANCH_INDEX] + b'\x75' + ORIGINAL[BRANCH_INDEX + 1:]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revert', action='store_true')
    args = parser.parse_args()
    before, after = (PATCHED, ORIGINAL) if args.revert else (ORIGINAL, PATCHED)
    metadata = TARGET.stat()
    with TARGET.open('r+b') as binary:
        header = binary.read(4096)
        if header[:4] != bytes.fromhex('cafebabe'):
            raise SystemExit('Unsupported Electron packaging: expected guarded universal binary')
        count = struct.unpack_from('>I', header, 4)[0]
        slices = [struct.unpack_from('>IIIII', header, 8 + 20 * n) for n in range(count)]
        matches = [s for s in slices if s[0] == 0x01000007]
        if len(matches) != 1:
            raise SystemExit('Expected exactly one x86_64 Electron slice')
        offset = matches[0][2] + FUNCTION_VA
        binary.seek(offset)
        actual = binary.read(len(ORIGINAL))
        if actual == after:
            print('Electron visibility already', 'restored' if args.revert else 'corrected')
            return
        if actual != before or ORIGINAL[BRANCH_INDEX] != 0x74:
            raise SystemExit('Electron visibility function differs; binary remains untouched')
        try:
            pid = int((Path.home() / '.darling/.init.pid').read_text().strip())
            state = next(line.split()[1] for line in Path(f'/proc/{pid}/status').read_text().splitlines() if line.startswith('State:'))
            if state != 'Z':
                raise SystemExit('Stop Darling before changing Electron visibility')
        except (FileNotFoundError, ValueError, StopIteration):
            pass
        binary.seek(offset + BRANCH_INDEX)
        binary.write(after[BRANCH_INDEX:BRANCH_INDEX + 1])
        binary.flush()
        os.fsync(binary.fileno())
    os.utime(TARGET, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    print('Electron visibility', 'restored' if args.revert else 'corrected')

if __name__ == '__main__':
    main()
