#!/usr/bin/env python3
"""Capture code-only exception stacks from the standalone signature probe."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('target')
parser.add_argument('--out', default='/tmp/riot-codesign-failures.out')
parser.add_argument('--binary', default='riot-codesign-check')
parser.add_argument('--security', default='@DARLING_SDK@/System/Library/Frameworks/Security.framework/Versions/A/Security')
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
out = Path(args.out)
probe_log = out.with_suffix('.probe.log')
env = os.environ.copy()
env.pop('ELECTRON_RUN_AS_NODE', None)
env['CODESIGN_WAIT'] = '1'
env['DYLD_LIBRARY_PATH'] = '@GUEST_HOME@/RuntimeLibraries'
with probe_log.open('w') as handle:
    probe = subprocess.Popen(['timeout', '45', 'darling',
        str(root / 'build' / args.binary), args.target], env=env,
        stdout=handle, stderr=handle)
    pid = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        match = re.search(r'CODESIGN_IMAGE base=(0x[0-9a-f]+)', probe_log.read_text())
        if match:
            base = int(match[1], 16)
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    if (entry / 'exe').readlink().name == 'mldr' and (
                        '/build/' + args.binary + '\n' in (entry / 'maps').read_text()):
                        pid = int(entry.name)
                        break
                except OSError:
                    pass
        if pid:
            break
        time.sleep(.1)
    if not pid:
        raise SystemExit('Standalone probe not found during its diagnostic wait')
    symbols = subprocess.check_output(['llvm-nm', '-n', args.security], text=True)
    offsets = []
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 3 and 'throwMe' in fields[-1] and any(
            name in fields[-1] for name in ['MacOSError', 'CssmError', 'CSError', 'CFError', 'UnixError']):
            offsets.append(int(fields[0], 16))
    script = f'''set pagination off
set confirm off
attach {pid}
python
import gdb,json
class ExceptionSite(gdb.Breakpoint):
 def stop(self):
  inf=gdb.selected_inferior();pc=int(gdb.parse_and_eval('$pc'))
  rsp=int(gdb.parse_and_eval('$rsp'));rbp=int(gdb.parse_and_eval('$rbp'))
  chain=[pc,int.from_bytes(bytes(inf.read_memory(rsp,8)),'little')]
  while rbp and len(chain)<18:
   raw=bytes(inf.read_memory(rbp,16));saved=int.from_bytes(raw[:8],'little');ret=int.from_bytes(raw[8:],'little');chain.append(ret)
   if saved<=rbp:break
   rbp=saved
  status=int(gdb.parse_and_eval('(int)$edi'))
  print('SIGNATURE_EXCEPTION '+json.dumps({{'status':status,'security_offsets':[hex(v-{base}) for v in chain]}}))
  return False
for offset in {offsets!r}: ExceptionSite('*'+hex({base}+offset))
end
continue
quit
'''
    commands = out.with_suffix('.gdb')
    commands.write_text(script)
    result = subprocess.run(['timeout', '30', 'gdb', '-nx', '-batch', '-x', str(commands)],
        capture_output=True, text=True)
    out.write_text(result.stdout + result.stderr)
    for line in result.stdout.splitlines():
        if line.startswith('SIGNATURE_EXCEPTION '):
            print(line, flush=True)
    probe.wait(timeout=15)
