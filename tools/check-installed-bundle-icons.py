#!/usr/bin/env python3
"""Decode installed bundle icons in place; never emit or copy image data.

Pass bundle paths explicitly. Requires Pillow with ICNS decoder support.
"""
import argparse
from pathlib import Path
import plistlib
import sys

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundles', nargs='+', type=Path)
    args = parser.parse_args()
    failures = 0
    for bundle in args.bundles:
        try:
            with (bundle / 'Contents/Info.plist').open('rb') as stream:
                name = plistlib.load(stream)['CFBundleIconFile']
            if not Path(name).suffix:
                name += '.icns'
            with Image.open(bundle / 'Contents/Resources' / name) as icon:
                icon.load()
                if icon.width < 1 or icon.height < 1:
                    raise ValueError('empty image')
            print(f'{bundle}: decoded')
        except (OSError, KeyError, ValueError) as exc:
            failures += 1
            print(f'{bundle}: failed: {exc}', file=sys.stderr)
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
