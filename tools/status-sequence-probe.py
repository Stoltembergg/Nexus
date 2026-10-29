#!/usr/bin/env python3
"""Build or explicitly launch the neutral timed tray probe, never Riot."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from probe_prefix import ProbePrefix

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/status-sequence-probe'


def build():
    config = json.loads((ROOT / 'build/config.json').read_text())
    folder = ROOT / 'build/darling-src/build/src/external/cocotron/AppKit'
    flags = {}
    for line in (folder / 'CMakeFiles/AppKit.dir/flags.make').read_text().splitlines():
        if line.startswith('C_') and ' = ' in line:
            name, value = line.split(' = ', 1)
            flags[name] = shlex.split(value)
    OUT.mkdir(parents=True, exist_ok=True)
    obj = OUT / 'probe.o'
    subprocess.run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'],
                    '-UNDEBUG', '-Wno-macro-redefined', '-c', str(ROOT / 'tools/status-sequence-probe.m'),
                    '-o', str(obj)], check=True)
    subprocess.run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
                    '-nostdlib', '-isysroot', config['sdk'], str(obj), '-lSystem', '-lobjc',
                    '-framework', 'AppKit', '-framework', 'Foundation', '-o', str(OUT / 'probe')], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('build', 'desktop'))
    parser.add_argument('--desktop', action='store_true', help='explicitly permit a real desktop tray item')
    parser.add_argument('--seconds', type=int, default=180, help='guest lifetime, 10..180 seconds (default 180)')
    args = parser.parse_args()
    if not 10 <= args.seconds <= 180:
        parser.error('--seconds must be between 10 and 180')
    if args.mode == 'build':
        build()
        return
    if not args.desktop:
        parser.error('desktop launch requires --desktop')
    config = json.loads((ROOT / 'build/config.json').read_text())
    binary = OUT / 'probe'
    stage = ROOT / 'build/status-count-title-diagnostic'
    wrapper = ROOT / 'build/libDarlingStatusNotifier.dylib'
    for path in (binary, stage / 'AppKit.framework/Versions/C/AppKit', wrapper):
        if not path.is_file():
            parser.error('missing artifact: ' + str(path))
    darling = shutil.which('darling')
    if not darling:
        parser.error('darling not found')
    # A new prefix per invocation; never reuse or stop a live namespace.
    owner = ProbePrefix(ROOT, 'sp-', 'prefix')
    prefix = owner.prefix
    try:
        if len(os.fsencode(str(prefix / 'var/run/shellspawn.sock'))) >= 108:
            parser.error('private prefix socket path exceeds Linux AF_UNIX limit: ' + str(prefix))
        guest = '/Volumes/SystemRoot'
        original_home = Path(config['prefix']) / config['guest_home'].lstrip('/')
        print('Private prefix:', prefix, flush=True)
        print(f'Neutral green icon; four hidden empty items for 8 seconds, then visible; exits after {args.seconds} seconds.', flush=True)
        environment = dict(os.environ, DPREFIX=str(prefix))
        environment.pop('SEQUENCE_TEST_SECONDS', None)
        subprocess.run([darling, 'shell', 'env',
                        'DYLD_FRAMEWORK_PATH=' + guest + str(stage) + ':' + guest + str(original_home / 'RuntimeFrameworks'),
                         'DYLD_LIBRARY_PATH=' + guest + str(original_home / 'RuntimeLibraries'),
                         'DARLING_STATUS_NOTIFIER_LIBRARY=' + guest + str(wrapper),
                         'SEQUENCE_TEST_SECONDS=' + str(args.seconds), guest + str(binary)],
                       env=environment, check=True)
    finally:
        owner.cleanup(darling)


if __name__ == '__main__':
    main()
