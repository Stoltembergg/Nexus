#!/usr/bin/env python3
"""Build only the opt-in native Linux tray transport; installs nothing."""
import argparse
from pathlib import Path
import shlex
import subprocess


def build(output):
    root = Path(__file__).resolve().parents[1]
    flags = shlex.split(subprocess.check_output(
        ['pkg-config', '--cflags', '--libs', 'gio-2.0'], text=True))
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-fPIC', '-shared', '-pthread',
                    str(root / 'tools/darling-status-notifier.c'),
                    str(root / 'tools/darling-dbus-menu.c'),
                    '-o', str(output), *flags], check=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(
        Path(__file__).resolve().parents[1] / 'build/libdarling-status-notifier.so'))
    print(build(parser.parse_args().output))
