#!/usr/bin/env python3
"""Prepare artifacts only; never launch a guest or modify an existing tree."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'build/darling-src/src/external/cocotron'


def run(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


def prepare(output, source, compile_artifacts=False, sdk=None, flags_file=None):
    output, source = Path(output).resolve(), Path(source).resolve()
    if output.exists() or output.is_relative_to(ROOT) or output.is_relative_to(source):
        raise ValueError('output must be a new directory outside the Nexus and source trees')
    if not output.parent.is_dir():
        raise ValueError('output parent must already exist')
    for tool in ('git', 'tar', 'patch'):
        if not shutil.which(tool):
            raise ValueError('missing prerequisite: ' + tool)
    revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    top = Path(subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--show-toplevel'], text=True).strip()).resolve()
    if top != source:
        raise ValueError('source must be the Cocotron git repository root')
    if compile_artifacts and (not sdk or not flags_file):
        raise ValueError('--compile requires --sdk and --flags-file')
    output.mkdir()
    archive = subprocess.run(['git', '-C', str(source), 'archive', revision, 'AppKit'], check=True, capture_output=True)
    run(['tar', '-xf', '-'], cwd=output, input=archive.stdout)
    for patch in (ROOT / 'patches/experimental/cocotron-status-notifier.patch', HERE / 'cocotron-reopen.patch'):
        run(['patch', '--batch', '--forward', '-p1', '-i', patch], cwd=output)
    manifest = {'cocotron_revision': revision, 'patches': ['cocotron-status-notifier.patch', 'cocotron-reopen.patch'],
                'appkit_built': False, 'guest_executed': False, 'artifacts_compiled': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if compile_artifacts:
        spec = importlib.util.spec_from_file_location('transport', HERE / 'build-transport.py')
        transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transport)
        native = transport.build(output / 'native')
        wrapper = output / 'libDarlingStatusNotifier.dylib'
        run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-dynamiclib', '-nostdlib',
             '-O2', '-Wall', '-Wextra', '-Werror', '-isysroot', sdk,
             '-I' + str(ROOT / 'build/darling-src/src/startup/mldr/elfcalls'),
             '-DDARLING_STATUS_HOST_LIBRARY="' + str(native) + '"', '-Wl,-undefined,dynamic_lookup',
             '-Wl,-install_name,@rpath/libDarlingStatusNotifier.dylib',
             ROOT / 'tools/status-notifier-native-wrapper.c', '-o', wrapper])
        flags = {}
        for line in Path(flags_file).read_text().splitlines():
            if line.startswith('C_') and ' = ' in line:
                key, value = line.split(' = ', 1)
                flags[key] = shlex.split(value)
        obj = output / 'probe.o'
        run(['clang', *flags['C_DEFINES'], *flags['C_INCLUDES'], *flags['C_FLAGS'], '-UNDEBUG',
             '-Wno-macro-redefined', '-c', HERE / 'probe.m', '-o', obj])
        run(['clang', '-target', 'x86_64-apple-macosx11.0', '-fuse-ld=lld', '-nostdlib',
             '-isysroot', sdk, obj, '-lSystem', '-lobjc', '-framework', 'AppKit',
             '-framework', 'Foundation', '-o', output / 'probe'])
        manifest['artifacts_compiled'] = True
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='nonexistent directory outside Nexus')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE, help='clean committed Cocotron git repository')
    parser.add_argument('--compile', action='store_true', help='also attempt native, wrapper and standalone probe builds')
    parser.add_argument('--sdk', help='Darling SDK sysroot (required with --compile)')
    parser.add_argument('--flags-file', help='existing AppKit flags.make (required with --compile)')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.output, args.source, args.compile, args.sdk, args.flags_file), indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit('preparation failed; any partial output was retained: ' + str(exc))


if __name__ == '__main__':
    main()
