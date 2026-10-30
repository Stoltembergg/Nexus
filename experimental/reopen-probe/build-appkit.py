#!/usr/bin/env python3
"""Rebuild impacted AppKit objects and relink into a private framework copy.

Requires the exact, up-to-date Makefile build and installed framework it reads.
No guest is started. Partial output is retained but never marked successful.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / 'build/darling-src/src/external/cocotron/AppKit'
BUILD = ROOT / 'build/darling-src/build/src/external/cocotron/AppKit'
PATCHES = (ROOT / 'patches/experimental/cocotron-status-notifier.patch', HERE / 'cocotron-reopen.patch')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output, framework):
    output, framework = Path(output).resolve(), Path(framework).resolve()
    if (output.exists() or not output.parent.is_dir() or
            any(output.is_relative_to(tree) or tree.is_relative_to(output)
                for tree in (ROOT.resolve(), framework))):
        raise ValueError('output must be a new directory disjoint from Nexus and the source framework')
    original_binary = framework / 'Versions/C/AppKit'
    if not original_binary.is_file() or original_binary.is_symlink() or not (framework / 'Versions/C/Resources').is_dir():
        raise ValueError('expected framework Versions/C/AppKit and Resources')
    if digest(original_binary) != digest(BUILD / 'AppKit'):
        raise ValueError('framework binary does not match the build being reused')
    patch_paths = set()
    for patch in PATCHES:
        paths = re.findall(r'^\+\+\+ b/AppKit/(.+)$', patch.read_text(), re.M)
        if not paths:
            raise ValueError('no AppKit patch paths in ' + str(patch))
        patch_paths.update(paths)
    if any(Path(p).is_absolute() or '..' in Path(p).parts for p in patch_paths):
        raise ValueError('unsafe patch path')
    changed_sources = {p for p in patch_paths if p.endswith('.m')}
    headers = {p for p in patch_paths if p.endswith('.h')}
    if changed_sources | headers != patch_paths:
        raise ValueError('unsupported patched file type')
    link = shlex.split((BUILD / 'CMakeFiles/AppKit.dir/link.txt').read_text())
    if link.count('-o') != 1 or link[link.index('-o') + 1] != 'AppKit':
        raise ValueError('unexpected link output')
    # Reject linker output-producing options; this script only accepts the known
    # CMake link shape, not arbitrary commands from a modified build tree.
    allowed_wl = ('-Wl,-dylib_install_name,', '-Wl,-compatibility_version,', '-Wl,-current_version,',
                  '-Wl,-sdk_version,', '-Wl,-dylib_file,', '-Wl,-reexport_library,', '-Wl,-rpath-link,')
    if any(x.startswith('-Wl,') and x != '-Wl,-Z' and not x.startswith(allowed_wl) for x in link):
        raise ValueError('unrecognized linker option')
    if any(x.startswith('@') or x in ('-Xlinker', '-save-temps', '-emit-llvm') for x in link):
        raise ValueError('unsafe link command')
    objects = [x for x in link if x.startswith('CMakeFiles/AppKit.dir/') and x.endswith('.o')]
    if not objects or len(objects) != len(set(objects)) or len(objects) != sum(x.endswith('.o') for x in link):
        raise ValueError('unexpected object mapping')
    source_map = {o: o.removeprefix('CMakeFiles/AppKit.dir/').removesuffix('.o') for o in objects}
    if not changed_sources <= set(source_map.values()):
        raise ValueError('patched source has no linked object')
    header_paths = {(SOURCE / h).resolve() for h in headers if (SOURCE / h).exists()}
    selected = []
    for obj, source in source_map.items():
        path = BUILD / obj
        depfile = BUILD / (obj + '.d')
        if not path.is_file() or not depfile.is_file() or not (SOURCE / source).is_file():
            raise ValueError('missing object, dependency file or source: ' + obj)
        words = shlex.split(depfile.read_text().replace('\\\n', ' '))
        if len(words) < 2 or not words[0].endswith(obj + ':'):
            raise ValueError('unexpected dependency file: ' + str(depfile))
        deps = [Path(x) for x in words[1:]]
        if any(not p.is_file() or p.stat().st_mtime_ns > path.stat().st_mtime_ns for p in deps):
            raise ValueError('missing or newer dependency for ' + obj)
        if source in changed_sources or {p.resolve() for p in deps} & header_paths:
            selected.append(obj)
    flags_text = (BUILD / 'CMakeFiles/AppKit.dir/flags.make').read_text()
    flags = dict((k, shlex.split(v)) for k, v in re.findall(r'^(C_\w+) = (.*)$', flags_text, re.M))
    custom = dict(re.findall(r'^# Custom flags: src/external/cocotron/AppKit/CMakeFiles/AppKit.dir/(\S+)\.o_FLAGS = (.*)$', flags_text, re.M))
    if flags_text.count('# Custom flags:') != len(custom):
        raise ValueError('unrecognized per-object flags')
    output.mkdir()
    shutil.copytree(SOURCE, output / 'AppKit', symlinks=True)
    # Writes via pre-existing source symlinks could escape the copy.
    for name in patch_paths:
        target = output / 'AppKit' / name
        if target.is_symlink() or not target.resolve().is_relative_to(output):
            raise ValueError('patched path escapes isolated tree: ' + name)
    for patch in PATCHES:
        subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)], cwd=output, check=True)
    includes = ['-I' + str(output / 'AppKit/include')]
    prefix = '-I' + str(SOURCE)
    includes += [('-I' + str(output / 'AppKit') + x[len(prefix):] if x.startswith(prefix) else x)
                 for x in flags['C_INCLUDES']]
    for obj in selected:
        source = source_map[obj]
        target = output / 'objects' / (source + '.o')
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([link[0], *flags['C_DEFINES'], *includes, *flags['C_FLAGS'],
                        *shlex.split(custom.get(source, '')), '-c', str(output / 'AppKit' / source),
                        '-o', str(target)], cwd=BUILD, check=True)
        link[link.index(obj)] = str(target)
    binary = output / 'AppKit-linked'
    link[link.index('-o') + 1] = str(binary)
    subprocess.run(link, cwd=BUILD, check=True)
    data = binary.read_bytes()
    if data[:4] != b'\xcf\xfa\xed\xfe' or not all(x in data for x in
       (b'_pollDarlingStatusItems:', b'_pollNativeEvents', b'_startDarlingPolling',
        b'DARLING_STATUS_NOTIFIER_LIBRARY', b'_reopen')):
        raise ValueError('linked binary lacks expected Mach-O or dispatch markers')
    symbols = subprocess.check_output(['llvm-nm', str(binary)], text=True)
    if not all(x in symbols for x in ('-[NSStatusBar _pollDarlingStatusItems:]',
                                      '-[NSStatusBar _startDarlingPolling]',
                                      '-[NSStatusItem _pollNativeEvents]')):
        raise ValueError('linked binary lacks required Objective-C method symbols')
    dest = output / 'AppKit.framework'
    shutil.copytree(framework, dest, symlinks=True)
    copied_binary = dest / 'Versions/C/AppKit'
    if copied_binary.is_symlink() or not copied_binary.resolve().is_relative_to(output):
        raise ValueError('framework binary escapes isolated tree')
    shutil.copyfile(binary, copied_binary)
    original_resources = framework / 'Versions/C/Resources'
    resources = dest / 'Versions/C/Resources'
    for path in original_resources.rglob('*'):
        relative = path.relative_to(original_resources)
        copy = resources / relative
        if path.is_symlink():
            if not copy.is_symlink() or copy.readlink() != path.readlink():
                raise ValueError('resource symlink mismatch: ' + str(relative))
        elif path.is_file() and (not copy.is_file() or digest(path) != digest(copy)):
            raise ValueError('resource mismatch: ' + str(relative))
        elif path.is_dir() and not copy.is_dir():
            raise ValueError('resource directory mismatch: ' + str(relative))
    manifest = {'appkit_built': True, 'guest_executed': False, 'objects_recompiled': selected,
                'patches_sha256': {p.name: digest(p) for p in PATCHES},
                'framework_sha256': digest(copied_binary)}
    (output / 'appkit-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    parser.add_argument('--framework', required=True, help='installed framework matching the build binary')
    args = parser.parse_args()
    try:
        result = build(args.output, args.framework)
        print('Built isolated framework; recompiled', len(result['objects_recompiled']), 'objects')
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit('isolated AppKit build failed; partial output retained: ' + str(exc))


if __name__ == '__main__':
    main()
