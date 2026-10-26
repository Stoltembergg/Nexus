#!/usr/bin/env python3
"""Probe PR #144's parser with our own Mach-O fixtures, without installing it.

No Darling, Riot, sudo, account access, signing-store changes or network calls.
An integration blocker produces exit 1, not a misleading successful readiness.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import uuid

PIN = '000d594436137f1077896166b2f22e3e7bf5a836'
ROOT = Path(__file__).resolve().parents[2]


def command(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True,
                          text=True, timeout=60, **kwargs)


def checked_source(source, allow_parser_edits=False):
    head = command(['git', '-C', source, 'rev-parse', 'HEAD']).stdout.strip()
    if head != PIN:
        raise ValueError('Source revision differs from the reviewed PR head')
    changes = command(['git', '-C', source, 'diff', '--name-only', 'HEAD']).stdout.splitlines()
    allowed = {'tools/dc-codesign/dc_codesign.c', 'patches/darling.patch', 'patches/darlingserver.patch'}
    if changes and (not allow_parser_edits or not set(changes).issubset(allowed)):
        raise ValueError('Modified source requires explicit permission for parser-only edits')
    return head, changes


def text_offset(data):
    """Find __text in an LLD-generated little-endian 64-bit synthetic image."""
    if len(data) < 32 or data[:4] != b'\xcf\xfa\xed\xfe':
        raise ValueError('Expected a 64-bit thin fixture')
    ncmds, sizeofcmds = struct.unpack_from('<II', data, 16)
    end, offset = 32 + sizeofcmds, 32
    if end > len(data):
        raise ValueError('Truncated load-command area')
    for _ in range(ncmds):
        if offset + 8 > end:
            raise ValueError('Truncated load command')
        kind, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > end:
            raise ValueError('Invalid load-command bounds')
        if kind == 0x19 and size >= 72:
            sections = struct.unpack_from('<I', data, offset + 64)[0]
            if 72 + sections * 80 > size:
                raise ValueError('Invalid section table')
            for index in range(sections):
                section = offset + 72 + index * 80
                if data[section:section + 16].rstrip(b'\0') == b'__text':
                    location = struct.unpack_from('<I', data, section + 48)[0]
                    if location >= len(data):
                        raise ValueError('Text section is outside fixture')
                    return location
        offset += size
    raise ValueError('No synthetic __text section')


def embedded_file(patch, filename):
    marker = f'diff --git a/{filename} b/{filename}\n'
    section = patch.split(marker, 1)[1].split('\ndiff --git ', 1)[0]
    return ''.join(line[1:] + '\n' for line in section.splitlines()
                   if line.startswith('+') and not line.startswith('+++'))


def parser_result(parser, operation, fixture):
    result = subprocess.run([str(parser), operation, str(fixture)],
                            capture_output=True, text=True, timeout=10)
    sanitizer = ('AddressSanitizer' in result.stderr or 'runtime error:' in result.stderr)
    if sanitizer or result.returncode not in (0, 1):
        raise RuntimeError('Parser crashed or sanitizer reported a failure')
    return result.returncode == 0


def run_lab(source, tools, allow_parser_edits=False):
    head, changes = checked_source(source, allow_parser_edits)
    report = {'schema': 1, 'pr': 144, 'head': head, 'local_changes': changes, 'client_started': False,
              'runtime_installed': False, 'account_accessed': False,
              'runtime_integration_validated': False, 'apple_trust_validated': False,
              'checks': [], 'integration_blockers': [],
              'notice': 'Synthetic parser observations only; no Apple trust or account-safety claim.'}
    parser_source = source / 'tools/dc-codesign/dc_codesign.c'
    canonical = parser_source.read_text()
    copies = (('patches/darling.patch', 'src/startup/mldr/dc_codesign.c'),
              ('patches/darlingserver.patch', 'src/dc_codesign.c'))
    for patch, filename in copies:
        same = embedded_file((source / patch).read_text(), filename) == canonical
        report['checks'].append({'name': 'parser-copy:' + patch, 'passed': same})
        if not same:
            report['integration_blockers'].append('Parser copy differs from canonical source: ' + patch)

    with tempfile.TemporaryDirectory(prefix='pr144-fixtures-', dir=ROOT / 'build') as directory:
        temporary = Path(directory)
        parser = temporary / 'parser'
        command([tools['clang'], '-D_GNU_SOURCE', '-std=c11', '-O1', '-g',
                 '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                 source / 'tools/dc-codesign/main.c', parser_source, '-lcrypto', '-o', parser])
        signed = {}
        for architecture, target in (('x86_64', 'x86_64-apple-macosx11.0'),
                                     ('arm64', 'arm64-apple-macosx11.0')):
            fixture = temporary / (architecture + '.dylib')
            command([tools['clang'], '-target', target, '-fuse-ld=lld', '-nostdlib', '-dynamiclib',
                     '-Wl,-adhoc_codesign', ROOT / 'research/pr144/fixture.c', '-o', fixture])
            signed[architecture] = fixture
        unsigned = temporary / 'unsigned.dylib'
        command([tools['clang'], '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld',
                 '-nostdlib', '-dynamiclib', '-Wl,-no_adhoc_codesign',
                 ROOT / 'research/pr144/fixture.c', '-o', unsigned])
        fat = temporary / 'universal.dylib'
        command([tools['llvm-lipo'], '-create', *signed.values(), '-output', fat])

        for architecture, fixture in signed.items():
            accepted = parser_result(parser, 'verify', fixture)
            report['checks'].append({'name': 'signed-thin:' + architecture, 'passed': accepted})
            if not accepted:
                raise RuntimeError('Positive signed fixture was not accepted')

        data = bytearray(signed['x86_64'].read_bytes())
        data[text_offset(data)] ^= 1
        tampered = temporary / 'tampered.dylib'
        tampered.write_bytes(data)
        for name, fixture in (('unsigned-rejected', unsigned), ('changed-text-rejected', tampered)):
            rejected = not parser_result(parser, 'verify', fixture)
            report['checks'].append({'name': name, 'passed': rejected})
            if not rejected:
                report['integration_blockers'].append(name + ': expected rejection did not occur')

        # This is a compatibility check, not an attempt to load the image.
        fat_accepted = parser_result(parser, 'verify', fat)
        report['checks'].append({'name': 'signed-universal-supported', 'passed': fat_accepted})
        if not fat_accepted:
            report['integration_blockers'].append(
                'Canonical parser rejects a signed universal image; the mldr gate invokes it before load() selects a slice.')

        # A parser must honor the declared command-table boundary even for info.
        original = signed['x86_64'].read_bytes()
        declared = struct.unpack_from('<I', original, 20)[0]
        for name, size in (('zero', 0), ('short', declared - 1), ('oversized', declared + 8)):
            malformed = bytearray(original)
            struct.pack_into('<I', malformed, 20, size)
            malformed_path = temporary / ('malformed-' + name + '.dylib')
            malformed_path.write_bytes(malformed)
            rejected = not parser_result(parser, 'info', malformed_path)
            report['checks'].append({'name': 'malformed-sizeofcmds-' + name + '-rejected', 'passed': rejected})
            if not rejected:
                report['integration_blockers'].append(
                    'dc_parse accepts inconsistent sizeofcmds (' + name + '); this info-only test does not demonstrate a verified image or loader exploit.')
    report['parser_checks_passed'] = not report['integration_blockers']
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Clean checkout of the pinned PR head')
    parser.add_argument('--allow-parser-edits', action='store_true',
                        help='Allow explicitly reviewed edits to the canonical parser and its two patch copies')
    args = parser.parse_args(argv)
    tools = {name: shutil.which(name) for name in ('clang', 'llvm-lipo')}
    if not all(tools.values()) or not shutil.which('ld64.lld'):
        parser.error('Requires clang, ld64.lld, llvm-lipo and OpenSSL development libraries')
    os.umask(0o077)
    (ROOT / 'build').mkdir(exist_ok=True)
    try:
        report = run_lab(args.source.resolve(), tools, args.allow_parser_edits)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print('Lab failed: check the pinned source, compiler and OpenSSL; no runtime was installed.')
        return 2
    output = ROOT / 'build' / ('pr144-parser-review-' + uuid.uuid4().hex + '.json')
    with output.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    for check in report['checks']:
        print(('PASS ' if check['passed'] else 'BLOCKER ') + check['name'])
    print('Private report:', output)
    return 0 if report['parser_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
