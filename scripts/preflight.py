#!/usr/bin/env python3
"""Read-only host prerequisites before an expensive build or runtime installation.

Never starts Darling/Riot, installs packages, collects account data or uploads.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys


def version(text):
    match = re.search(r'\b(\d+)\.(\d+)(?:\.(\d+))?', text)
    return tuple(int(n or 0) for n in match.groups()) if match else None


def query(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
        return None
    return result.stdout


def vulkan_capability(text):
    """Require API and timelineSemaphore on the same physical device.

    Return True for at least one capable device, False for definitively
    unsupported devices, None for an incomplete/unrecognized inventory.
    """
    devices = re.split(r'^GPU\d+:\s*$', text, flags=re.M)[1:]
    if not devices:
        return None
    incomplete = False
    for device in devices:
        api = re.search(r'^\s*apiVersion\s*=\s*([\d.]+)', device, re.M)
        timeline = re.findall(r'^\s*timelineSemaphore\s*=\s*(true|false)\b', device, re.M)
        api_version = version(api[1]) if api else None
        if api_version is None or not timeline or len(set(timeline)) != 1:
            incomplete = True
            continue
        if api_version >= (1, 3, 0) and timeline[0] == 'true':
            return True
    return None if incomplete else False


def run_checks(mode='build', *, which=None, probe=None, kernel=None, machine=None,
               python_version=None, environ=None, system=None):
    which = shutil.which if which is None else which
    probe = query if probe is None else probe
    kernel = platform.release() if kernel is None else kernel
    machine = platform.machine() if machine is None else machine
    python_version = sys.version_info[:3] if python_version is None else python_version
    env = os.environ if environ is None else environ
    system = platform.system() if system is None else system
    checks = []

    def add(name, status, message):
        checks.append({'name': name, 'status': status, 'message': message})

    def tool_version(name, minimum, arguments=('--version',)):
        executable = which(name)
        if executable is None:
            add(name, 'error', f'Install {name} and make it available on PATH.')
            return None
        output = probe([executable, *arguments])
        found = version(output) if output is not None else None
        if found is None:
            add(name, 'error', f'Could not determine {name} version; check the selected executable.')
        elif found < minimum:
            add(name, 'error', f'{name} {".".join(map(str, found))} is too old; '
                f'requires >= {".".join(map(str, minimum))}.')
        else:
            add(name, 'ok', f'{name} {".".join(map(str, found))}.')
        return found

    add('architecture', 'ok' if machine == 'x86_64' else 'error', 'Requires an x86-64 host.')
    add('python', 'ok' if tuple(python_version) >= (3, 12, 0) else 'error',
        'This source tree requires Python >= 3.12; newer upstream proposals are not yet integrated.')
    found_kernel = version(kernel)
    add('kernel', 'ok' if found_kernel and found_kernel >= (5, 14, 0) else 'error',
        'Linux >= 5.14 is required for allocator page-reuse hints.')
    if system != 'Linux':
        add('system', 'error', 'This integration supports Linux hosts only.')
    tool_version('cmake', (3, 20, 0))
    tool_version('git-lfs', (2, 13, 0), ('version',))
    clang = tool_version('clang', (16, 0, 0))
    llvm = tool_version('llvm-config', (16, 0, 0), ('--version',))
    if clang and llvm:
        if clang[0] != llvm[0]:
            add('llvm-alignment', 'error', 'Clang and llvm-config major versions differ; select a matching toolchain.')
        elif llvm[0] not in (22, 23):
            add('llvm-alignment', 'warning', 'Matching LLVM tools found; this patch set primarily tracks LLVM 22/23.')
        else:
            add('llvm-alignment', 'ok', 'Clang and llvm-config major versions match.')
    for name in ('llvm-objdump', 'llvm-nm'):
        found = tool_version(name, (16, 0, 0))
        if found and llvm and found[0] != llvm[0]:
            add(name + '-alignment', 'error', f'{name} differs from llvm-config; add the matching LLVM bindir to PATH.')
    for name in ('git', 'make', 'curl', 'unzip', 'pkg-config'):
        add(name, 'ok' if which(name) else 'error', f'{name} must be available on PATH.')
    pkg = which('pkg-config')
    if pkg:
        headers = probe([pkg, '--modversion', 'vulkan'])
        found = version(headers) if headers is not None else None
        add('vulkan-headers', 'ok' if found and found >= (1, 3, 0) else 'error',
            'Install Vulkan development headers >= 1.3 with pkg-config metadata.')

    graphics_failure = 'error' if mode == 'runtime' else 'warning'
    vulkan = which('vulkaninfo')
    if vulkan:
        output = probe([vulkan])
        capability = vulkan_capability(output) if output is not None else None
        if capability is True:
            add('vulkan-device', 'ok', 'At least one device reports Vulkan >= 1.3 and timeline semaphores.')
        elif capability is False:
            add('vulkan-device', graphics_failure, 'No enumerated device satisfies Vulkan >= 1.3 plus timeline semaphores.')
        else:
            add('vulkan-device', graphics_failure, 'Could not verify Vulkan device capabilities; check vulkaninfo and the driver.')
    else:
        add('vulkan-device', graphics_failure, 'Install vulkaninfo to verify runtime GPU capabilities.')

    if not env.get('DISPLAY'):
        add('x11', graphics_failure, 'No DISPLAY set; runtime installation requires an accessible X11/Xwayland display.')
    else:
        display_tool = which('xdpyinfo') or which('glxinfo')
        if display_tool is None:
            add('x11', 'warning', 'Display access is unverified; install xdpyinfo or glxinfo to probe it.')
        else:
            args = [display_tool] if which('xdpyinfo') == display_tool else [display_tool, '-B']
            accessible = probe(args) is not None
            add('x11', 'ok' if accessible else graphics_failure,
                'Display access verified.' if accessible else
                'Display access failed; check DISPLAY and XAUTHORITY in this session.')
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('build', 'runtime'), default='build')
    parser.add_argument('--json', action='store_true', help='Print aggregate checks, not command output or environment values')
    args = parser.parse_args(argv)
    checks = run_checks(args.mode)
    failed = any(check['status'] == 'error' for check in checks)
    if args.json:
        print(json.dumps({'schema': 1, 'mode': args.mode, 'passed': not failed, 'checks': checks}, indent=2))
    else:
        for check in checks:
            print(f"{check['status'].upper()}: {check['name']}: {check['message']}")
        print('Preflight failed; no build/runtime actions performed.' if failed else
              'Preflight passed. This is not a runtime, account-safety or Riot-approval guarantee.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
