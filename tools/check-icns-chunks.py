#!/usr/bin/env python3
"""Read ICNS files in place and report modern payloads; validate PNG framing."""
import argparse
from pathlib import Path
import struct
import zlib


def check(path):
    data = path.read_bytes()
    if len(data) < 8 or data[:4] != b'icns' or struct.unpack_from('>I', data, 4)[0] != len(data):
        raise ValueError('invalid ICNS header')
    offset, modern = 8, []
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError('truncated ICNS chunk')
        kind, size = struct.unpack_from('>4sI', data, offset)
        if size < 8 or size > len(data) - offset:
            raise ValueError('invalid ICNS chunk length')
        if kind in (b'ic08', b'ic09'):
            png = data[offset + 8:offset + size]
            if png.startswith(b'\x00\x00\x00\x0cjP  \r\n\x87\n') or png.startswith(b'\xff\x4f\xff\x51'):
                modern.append(kind.decode('ascii') + ':JPEG2000 (unsupported)')
                offset += size
                continue
            if png[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('modern chunk is not PNG')
            pos, first, ended = 8, True, False
            while pos < len(png):
                if len(png) - pos < 12:
                    raise ValueError('truncated PNG chunk')
                n, tag = struct.unpack_from('>I4s', png, pos)
                if n > len(png) - pos - 12:
                    raise ValueError('invalid PNG chunk length')
                end = pos + 12 + n
                if zlib.crc32(png[pos + 4:end - 4]) != struct.unpack_from('>I', png, end - 4)[0]:
                    raise ValueError('PNG CRC mismatch')
                if first:
                    expected = 256 if kind == b'ic08' else 512
                    if tag != b'IHDR' or n != 13 or struct.unpack_from('>II', png, pos + 8) != (expected, expected):
                        raise ValueError('invalid PNG IHDR')
                    first = False
                pos = end
                if tag == b'IEND':
                    ended = n == 0 and pos == len(png)
                    break
            if not ended:
                raise ValueError('missing PNG IEND')
            modern.append(kind.decode('ascii') + ':PNG (framing and CRC valid)')
        offset += size
    if not modern:
        raise ValueError('no supported modern chunks')
    return ','.join(modern)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('icons', type=Path, nargs='+')
    args = parser.parse_args()
    for icon in args.icons:
        print(f'{icon}: {check(icon)}')
