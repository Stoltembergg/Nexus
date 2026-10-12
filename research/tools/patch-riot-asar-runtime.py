#!/usr/bin/env python3
"""Guarded, size-preserving Riot UX asset streaming and CSP fixes.

The launcher verifies app.asar's size and mtime, and Electron reads its asar
header. This edits only bytes inside two existing files, preserving all three.
Run with --revert to restore the original bytes of this Riot release.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


DEFAULT_ARCHIVE = (Path.home() / '.darling/Applications/Riot Client.app/Contents/'
                   'Frameworks/Riot Client.app/Contents/Resources/app.asar')
OLD_STREAM = b'te=l.createReadStream(R,U);'
NEW_STREAM = b'te=l.createReadStream(R,{...U,highWaterMark:1048576});'
DEBUG_ID = b'//# debugId=1d18f9b5-984e-568d-a1f6-c925f20bdd63'
PADDING = b' ' * (len(DEBUG_ID) - (len(NEW_STREAM) - len(OLD_STREAM)))
OLD_CSP = b'http://www.youtube.com'
NEW_CSP = b"'unsafe-inline'       "


def extract(archive, name, tempdir):
    subprocess.run(['asar', 'extract-file', str(archive), name],
                   cwd=tempdir, check=True, capture_output=True)
    return (Path(tempdir) / Path(name).name).read_bytes()


def replace_member(data, old, new, label):
    if len(old) != len(new):
        raise ValueError(f'{label}: replacement changes member size')
    pos = data.find(old)
    if pos < 0 or data.count(old) != 1:
        raise ValueError(f'{label}: archive member is missing or ambiguous')
    data[pos:pos + len(old)] = new
    return pos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--revert', action='store_true')
    args = parser.parse_args()
    archive = args.archive
    stat = archive.stat()
    data = bytearray(archive.read_bytes())
    with tempfile.TemporaryDirectory(prefix='riot-asar-patch-') as tempdir:
        main_js = extract(archive, 'dist/main/main.js', tempdir)
        index = extract(archive, 'dist/renderer/index.html', tempdir)

    if args.revert:
        if main_js.count(NEW_STREAM) != 1 or index.count(NEW_CSP) != 1:
            raise SystemExit('archive is not in the expected patched state')
        if main_js[-len(PADDING)-1:-1] != PADDING:
            raise SystemExit('main.js debug ID padding differs from expected')
        new_main = main_js.replace(NEW_STREAM, OLD_STREAM)
        new_main = new_main[:-len(PADDING)-1] + DEBUG_ID + b'\n'
        new_index = index.replace(NEW_CSP, OLD_CSP)
    else:
        if main_js.count(NEW_STREAM) == 1 and index.count(NEW_CSP) == 1:
            print('already patched')
            return
        if main_js.count(OLD_STREAM) != 1 or main_js.count(DEBUG_ID) != 1:
            raise SystemExit('main.js differs from expected Riot release')
        if index.count(OLD_CSP) != 1:
            raise SystemExit('index.html differs from expected Riot release')
        new_main = main_js.replace(OLD_STREAM, NEW_STREAM).replace(DEBUG_ID, PADDING)
        new_index = index.replace(OLD_CSP, NEW_CSP)

    main_pos = replace_member(data, main_js, new_main, 'main.js')
    index_pos = replace_member(data, index, new_index, 'index.html')
    if len(data) != stat.st_size:
        raise AssertionError('archive size changed')
    with tempfile.NamedTemporaryFile(dir=archive.parent, prefix='.app.asar-m58-',
                                     delete=False) as output:
        output.write(data)
        temp_path = Path(output.name)
    os.chmod(temp_path, stat.st_mode)
    os.utime(temp_path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    os.replace(temp_path, archive)
    print(('reverted' if args.revert else 'patched'), archive,
          f'main offset={main_pos}', f'index offset={index_pos}',
          f'size={archive.stat().st_size}', f'mtime_ns={archive.stat().st_mtime_ns}')


if __name__ == '__main__':
    main()
