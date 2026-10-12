#!/usr/bin/env python3
"""Verify real signatures and reject executable/metadata tampering in copies."""
from pathlib import Path
import os
import plistlib
import re
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
lol = Path.home() / '.darling/Applications/League of Legends.app/Contents/LoL/LeagueClient.app'
framework = lol / 'Contents/Frameworks/mvg.framework'
fixtures = root / 'build/riot-signature-fixtures'
fixtures.mkdir(exist_ok=True)
tampered = fixtures / 'tampered-mvg'
shutil.copy2(framework / 'mvg', tampered)
with tampered.open('r+b') as handle:
    handle.seek(0x5000)
    byte = handle.read(1)
    handle.seek(0x5000)
    handle.write(bytes([byte[0] ^ 1]))
metadata = fixtures / 'metadata-mvg.framework'
shutil.copytree(framework, metadata, dirs_exist_ok=True)
info = metadata / 'Info.plist'
value = plistlib.loads(info.read_bytes())
value['CFBundleVersion'] = str(value.get('CFBundleVersion', '')) + '-modified'
info.write_bytes(plistlib.dumps(value))
targets = [str(framework).removeprefix(str(Path.home() / '.darling')),
           str(lol / 'Contents/MacOS/LeagueClient').removeprefix(str(Path.home() / '.darling')),
           '/Volumes/SystemRoot' + str(tampered), '/Volumes/SystemRoot' + str(metadata)]
env = os.environ.copy()
env.pop('ELECTRON_RUN_AS_NODE', None)
env.pop('CODESIGN_WAIT', None)
env.pop('DYLD_INSERT_LIBRARIES', None)
env['DYLD_LIBRARY_PATH'] = '@GUEST_HOME@/RuntimeLibraries'
result = subprocess.run(['darling', str(root / 'build/riot-codesign-check'), *targets],
                        env=env, capture_output=True, text=True, timeout=60)
lines = [line for line in result.stdout.splitlines() if line.startswith('CODESIGN')]
for line in lines:
    print(line)
text = '\n'.join(lines)
for case in range(3):
    assert f'parser_case={case} status=0 ' in text, 'valid requirement rejected'
assert 'parser_case=3 status=-67052 ' in text, 'malformed requirement accepted'
for target in [1, 2]:
    assert f'target={target} validity=0 ' in text, 'genuine signature rejected'
    assert f'target={target} false_requirement=-67050 ' in text, 'false requirement accepted'
for target in [3, 4]:
    match = re.search(rf'target={target} validity=(-?\d+)', text)
    assert match and int(match[1]) == -67030, 'modified signed content not rejected by signature check'
print('CODESIGN_REGRESSION pass=1')
